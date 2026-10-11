"""Rev3.7 foreground-only single top-level Gateway entrypoint.

Static mapping from the FOUR frozen Catalog capabilities to one exact
Backend and canonical UI resource arbiter. A separately authenticated
first-party caller supplies request DATA only; neither caller JSON nor
runtime flags can grant identity, policy, approval, readiness, or replay.

No daemon, alternate server, TaskQueue, PR CI, or second Publisher.
Whole-PRD source-development candidate; all production gates remain CLOSED.
"""
from __future__ import annotations

from typing import Any, Mapping

from automation.capability_catalog import load_catalog
from automation.capability_job_store import CapabilityStoreError
from automation.effective_policy import resolve_effective_policy
from automation.gateway_coordinator import (
    ForegroundCoordinator, TrustedInvocation,
)
from automation.local_fixed_backends import LocalFixedBackend
from automation.canonical_ui_resource import CanonicalUIResource
from automation.runtime_evidence_producer import (
    EvidenceProductionUnavailable, publish_pre_admission_readonly,
)

_ENTRYPOINT_RELEASE_ACCEPTED = False
_BACKEND_TYPES = {
    "android.device.observe": ("observation", False),
    "android.ui.workflow": ("ui_workflow", True),
    "android.root.exec": ("root_exec", False),
    "tiktok.publish": ("publisher", True),
}


class ForegroundEntrypointUnavailable(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def foreground_invoke(
    request: Mapping[str, Any],
) -> dict[str, Any]:
    """In-process once-only invocation with exact immutable request."""
    if not _ENTRYPOINT_RELEASE_ACCEPTED:
        return {
            "status": "BLOCKED",
            "reason_code": "FOREGROUND_ENTRYPOINT_RELEASE_GATE_CLOSED",
            "execution_authorized": False,
            "backend_submitted": False,
            "external_effect_attempts": 0,
        }
    if not isinstance(request, Mapping):
        raise ForegroundEntrypointUnavailable("REQUEST_CONTRACT_INVALID")
    capability = request.get("capability")
    if capability not in _BACKEND_TYPES:
        raise ForegroundEntrypointUnavailable(
            "CAPABILITY_NOT_REGISTERED")
    catalog = load_catalog()
    entry = catalog.get(capability)
    if not isinstance(entry, Mapping):
        raise ForegroundEntrypointUnavailable(
            "CAPABILITY_CATALOG_ENTRY_MISSING")
    backend_type, needs_ui = _BACKEND_TYPES[capability]
    if entry.get("enabled") is not True:
        raise ForegroundEntrypointUnavailable(
            "CAPABILITY_NOT_ACTIVATED")
    policy = resolve_effective_policy(entry).as_dict()
    # Source-stable policy and backend mapping only; a request cannot
    # supply approval, resource_guard, elevated route or fallback.
    frozen_request = dict(request)
    try:
        publish_pre_admission_readonly(
            request=frozen_request, effective_policy=policy,
        )
    except EvidenceProductionUnavailable as exc:
        raise ForegroundEntrypointUnavailable(exc.code) from exc
    payload = frozen_request.get("payload")
    if not isinstance(payload, Mapping):
        raise ForegroundEntrypointUnavailable("JOB_PAYLOAD_INVALID")
    if capability == "tiktok.publish":
        mode = payload.get("publish_mode")
        if mode not in {"DRY_RUN", "COMMIT"}:
            raise ForegroundEntrypointUnavailable(
                "PUBLISH_MODE_INVALID")
        dry_run = mode == "DRY_RUN"
    else:
        # For other capabilities the side-effect classification belongs
        # to static Catalog policy/adapter, not a user-selected dry_run.
        dry_run = capability == "android.device.observe"
    invocation = TrustedInvocation(
        request=frozen_request,
        contract={
            "capability": capability,
            "version": entry["version"],
        },
        policy=policy,
        runtime_facts={},
        identity_facts={},
        backend_type=backend_type,
        ui_resource_required=needs_ui,
        dry_run=dry_run,
    )
    return ForegroundCoordinator(
        backend=LocalFixedBackend(),
        resource=CanonicalUIResource(),
    ).invoke(invocation)
