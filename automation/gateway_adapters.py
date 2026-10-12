"""Rev3.7 static adapter mapping — wrap existing backends, do not rewrite.

Adapters only validate/translate immutable request payloads. They do NOT
acquire/release android_ui, allocate Backend IDs, decide approval/policy,
or own durable lifecycle. No extension/plugin discovery or scheduler.

Backend dispatch is owned by the dormant ForegroundCoordinator, subject to
the exact manifest, resource/session and effect-boundary contracts.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Callable, Mapping

_ID = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")


class AdapterContractError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class AdapterIntent:
    capability: str
    backend_type: str
    backend_identity: str
    immutable_request_sha256: str
    payload: dict[str, Any]
    needs_android_ui: bool
    unsafe_external_effect: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "capability": self.capability,
            "backend_type": self.backend_type,
            "backend_job_id": self.backend_identity,
            "request_sha256": self.immutable_request_sha256,
            "payload": self.payload,
            "needs_android_ui": self.needs_android_ui,
            "unsafe_external_effect": self.unsafe_external_effect,
            "execution_authorized": False,
        }


def _required(condition: bool, code: str) -> None:
    if not condition:
        raise AdapterContractError(code)


def _digest(value: Any) -> bool:
    return isinstance(value, str) and _SHA.fullmatch(value) is not None


def _basic(capability: str, source: Mapping[str, Any],
           backend_id: str, request_sha: str, expected_backend: str) -> None:
    _required(type(source) is dict, "CAPABILITY_PAYLOAD_INVALID")
    _required(isinstance(backend_id, str)
              and _ID.fullmatch(backend_id) is not None,
              "BACKEND_IDENTITY_INVALID")
    _required(_digest(request_sha), "REQUEST_IDENTITY_INVALID")
    for prohibited in (
        "approval", "resource_guard", "effective_policy", "resource",
        "backend_job_id", "claim_id", "owner_id", "route_override",
        "max_frame_age_ms", "auto_retry", "published",
    ):
        _required(prohibited not in source, "CALLER_CONTROLLED_AUTHORITY_DENIED")


def _tiktok(payload: Mapping[str, Any], backend_id: str,
            request_sha: str) -> AdapterIntent:
    _basic("tiktok.publish", payload, backend_id, request_sha, "publisher")
    _required(payload.get("publish_mode") in {"DRY_RUN", "COMMIT"},
              "TIKTOK_PUBLISH_MODE_INVALID")
    _required(payload.get("visibility") == "PUBLIC",
              "TIKTOK_VISIBILITY_UNSUPPORTED")
    _required(_digest(payload.get("content_sha256"))
              and _digest(payload.get("caption_sha256")),
              "TIKTOK_ARTIFACT_IDENTITY_INVALID")
    artifact = payload.get("existing_publisher_job_id")
    _required(isinstance(artifact, str) and
              _ID.fullmatch(artifact) is not None,
              "PUBLISHER_JOB_ID_INVALID")
    _required(payload.get("app_ui_contract_version")
              == "tiktok-ui-v1-CANDIDATE",
              "APP_UI_CONTRACT_MISMATCH")
    if payload["publish_mode"] == "COMMIT":
        from automation.trusted_ingress_approval import _URL
        url = payload.get("source_url")
        _required(isinstance(url, str)
                  and _URL.fullmatch(url) is not None,
                  "TIKTOK_EXPLICIT_SOURCE_URL_REQUIRED")
    return AdapterIntent(
        "tiktok.publish", "publisher", backend_id, request_sha,
        {
            "existing_publisher_job_id": artifact,
            "content_sha256": payload["content_sha256"],
            "caption_sha256": payload["caption_sha256"],
            "visibility": "PUBLIC",
            "publish_mode": payload["publish_mode"],
            "app_ui_contract_version": payload["app_ui_contract_version"],
            "source_url": payload.get("source_url"),
        },
        True, payload["publish_mode"] == "COMMIT",
    )


def _ui(payload: Mapping[str, Any], backend_id: str,
        request_sha: str) -> AdapterIntent:
    _basic("android.ui.workflow", payload, backend_id, request_sha,
           "ui_workflow")
    workflow = payload.get("workflow_contract_id")
    _required(isinstance(workflow, str)
              and _ID.fullmatch(workflow) is not None,
              "UI_WORKFLOW_CONTRACT_INVALID")
    _required(_digest(payload.get("workflow_sha256")),
              "UI_WORKFLOW_IDENTITY_INVALID")
    _required(payload.get("route_class") in {
        "SEMANTIC_UI", "VERIFIED_NOOP",
    }, "UNACCEPTED_UI_ROUTE")
    return AdapterIntent(
        "android.ui.workflow", "ui_workflow", backend_id, request_sha,
        {
            "workflow_contract_id": workflow,
            "workflow_sha256": payload["workflow_sha256"],
            "route_class": payload["route_class"],
        }, True, False,
    )


def _observe(payload: Mapping[str, Any], backend_id: str,
             request_sha: str) -> AdapterIntent:
    _basic("android.device.observe", payload, backend_id, request_sha,
           "observation")
    _required(payload.get("observer_version") == 1,
              "OBSERVATION_CONTRACT_UNAVAILABLE")
    return AdapterIntent(
        "android.device.observe", "observation", backend_id, request_sha,
        {"observer_version": 1}, False, False,
    )


def _root(payload: Mapping[str, Any], backend_id: str,
          request_sha: str) -> AdapterIntent:
    _basic("android.root.exec", payload, backend_id, request_sha,
           "root_exec")
    # No arbitrary root shell from request. Only versioned static maintenance
    # contract names are eligible; actual ADMIN dispatch must durable-bump
    # epoch for UNKNOWN state effects BEFORE shell execution.
    contract = payload.get("maintenance_contract_id")
    _required(contract in {"read-only-system-info.v1"},
              "ROOT_MAINTENANCE_CONTRACT_UNACCEPTED")
    return AdapterIntent(
        "android.root.exec", "root_exec", backend_id, request_sha,
        {"maintenance_contract_id": contract,
         "state_effect": "UNKNOWN",
         "admin_epoch_bump_required": True},
        False, False,
    )


ADAPTERS: dict[str, Callable[[Mapping[str, Any], str, str], AdapterIntent]] = {
    "tiktok.publish": _tiktok,
    "android.ui.workflow": _ui,
    "android.device.observe": _observe,
    "android.root.exec": _root,
}


def prepare_adapter_intent_readonly(
    *, capability: str, immutable_payload: Mapping[str, Any],
    exact_backend_id: str, exact_request_sha256: str,
) -> dict[str, Any]:
    """No resource claim, subprocess, network, click or top-level job."""
    adapter = ADAPTERS.get(capability)
    if adapter is None:
        raise AdapterContractError("CAPABILITY_ADAPTER_NOT_REGISTERED")
    result = adapter(immutable_payload, exact_backend_id,
                     exact_request_sha256)
    return result.as_dict()
