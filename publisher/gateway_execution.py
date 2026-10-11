"""Rev3.7 scoped integration into the EXISTING TikTok Publisher.

Gateway may use the existing publish_job helpers and generic_tiktok
controller, but may NOT enter the Legacy wake/unlock/claim path.
There is exactly one android_ui claim, acquired by the top-level Gateway.

IMPORTANT: This code path is CLOSED and has no verified production
Android action-time observer. Its callable shape is implementation work
only, not approval to publish or even run a DRY_RUN on the tablet.
"""
from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping
import json
import re

from automation import resource_arbiter
from automation.capability_job_store import (
    AdmittedJob, CapabilityStoreError, _read_json, _need, _sha,
)
from automation.publisher_boundary_guard import (
    PublisherBoundaryError, read_gateway_binding,
    verify_before_publisher_committing,
)

_GATEWAY_PUBLISHER_EXECUTION_ACCEPTED = False
_SHA = re.compile(r"^[0-9a-f]{64}$")
_ID = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


class GatewayPublisherUnavailable(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ExactPublisherContext:
    capability_job_id: str
    backend_job_id: str
    publisher_job_id: str
    request_sha256: str
    effective_policy_sha256: str
    content_sha256: str
    caption_sha256: str
    manifest_sha256: str
    publish_mode: str
    claim_id: str
    owner_id: str

    def resource_guard(self) -> dict[str, str]:
        return {
            "resource": "android_ui",
            "claim_id": self.claim_id,
            "owner_id": self.owner_id,
        }


def _sync_directory(path: Path) -> None:
    """Durably persist Publisher archive path rename before final receipt."""
    import os
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _require(predicate: bool, code: str) -> None:
    if not predicate:
        raise GatewayPublisherUnavailable(code)


def _verify_preexisting_context(
    *, publisher_job: Path,
    manifest: Mapping[str, Any],
    provided: Mapping[str, Any],
) -> ExactPublisherContext:
    """Only observe owner-protected durable binding and current claim."""
    bound = read_gateway_binding(publisher_job, manifest)
    _require(bound is not None, "GATEWAY_BINDING_NOT_PRESENT")
    for field in (
        "capability_job_id", "backend_job_id", "publisher_job_id",
        "request_sha256", "effective_policy_sha256", "content_sha256",
        "caption_sha256", "manifest_sha256", "publish_mode",
        "claim_id", "owner_id",
    ):
        _require(bound.get(field) == provided.get(field)
                 and isinstance(bound.get(field), str) and bound[field],
                 "GATEWAY_BINDING_IDENTITY_MISMATCH")
    context = ExactPublisherContext(**{
        field: bound[field] for field in (
            "capability_job_id", "backend_job_id", "publisher_job_id",
            "request_sha256", "effective_policy_sha256", "content_sha256",
            "caption_sha256", "manifest_sha256", "publish_mode",
        "claim_id", "owner_id",
        )
    })
    _require(bool(_ID.fullmatch(context.publisher_job_id))
             and bool(_SHA.fullmatch(context.request_sha256))
             and bool(_SHA.fullmatch(context.effective_policy_sha256))
             and bool(_SHA.fullmatch(context.content_sha256))
             and bool(_SHA.fullmatch(context.caption_sha256))
             and bool(_SHA.fullmatch(context.manifest_sha256))
             and context.publish_mode in {"DRY_RUN", "COMMIT"},
             "GATEWAY_BINDING_INVALID")
    _require(context.publisher_job_id == manifest.get("job_id"),
             "PUBLISHER_MANIFEST_MISMATCH")
    try:
        claim = resource_arbiter.assert_guard(context.resource_guard())
    except resource_arbiter.ResourceError as exc:
        raise GatewayPublisherUnavailable("RESOURCE_OWNERSHIP_MISMATCH") from exc
    _require(claim.get("owner_kind") == "CAPABILITY"
             and claim.get("capability_job_id") == context.capability_job_id
             and claim.get("backend_job_id") == context.backend_job_id
             and claim.get("request_sha256") == context.request_sha256,
             "CAPABILITY_RESOURCE_IDENTITY_MISMATCH")
    return context


def _require_existing_unlocked_screen() -> None:
    """Conservative preflight with no wake/unlock/input side effects.

    These shell observations are NOT a substitute for the independent
    action-time native Android Driver check. Unknown output fails closed.
    """
    import subprocess
    from automation.authoritative_state_reader import (
        observe_authoritative_state, AuthorityUnavailable,
    )
    from publisher import publish_job as old
    try:
        observe_authoritative_state()
        power = subprocess.run(
            [str(old.ANDROIDCTL), "screen-state"],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=20)
        keyguard = subprocess.run(
            [str(old.ANDROIDCTL), "keyguard-state"],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=20)
    except (AuthorityUnavailable, OSError, subprocess.SubprocessError) as exc:
        raise GatewayPublisherUnavailable(
            "GATEWAY_SCREEN_OBSERVER_UNAVAILABLE") from exc
    # A screen being powered is NOT proof that the secure keyguard has
    # cleared. Only known positive device-provided predicates count.
    import re
    # Require TWO independent exact keyguard predicates, not a substring
    # which can match a different dumpsys field. Unknown/missing/conflicting
    # OEM output is NOT evidence that secure keyguard is unlocked.
    raw = (keyguard.stdout or "").lower()
    facts: dict[str, bool] = {}
    for field in ("mshowing", "minputrestricted"):
        values = re.findall(
            rf"(?<![a-z0-9_]){field}\s*=\s*(true|false)(?![a-z0-9_])",
            raw)
        if len(values) != 1:
            raise GatewayPublisherUnavailable(
                "GATEWAY_KEYGUARD_FACTS_AMBIGUOUS")
        facts[field] = values[0] == "true"
    awake = re.findall(
        r"(?<![a-z0-9_])mwakefulness\s*=\s*(awake|asleep|dozing|dreaming)"
        r"(?![a-z0-9_])", (power.stdout or "").lower())
    if (len(awake) != 1 or awake[0] != "awake"
            or facts["mshowing"] or facts["minputrestricted"]):
        raise GatewayPublisherUnavailable(
            "GATEWAY_SCREEN_NOT_POSITIVELY_UNLOCKED")


def execute_gateway_bound(
    *, publisher_job: Path,
    manifest: Mapping[str, Any],
    binding: Mapping[str, Any],
    trusted_runtime_context: Mapping[str, Any] | None,
    trusted_effect_callback: Callable[[], Mapping[str, Any]] | None,
) -> dict[str, Any]:
    """Prospective new Gateway entrypoint, not a second Publisher.

    A future accepted coordinator MUST supply an authenticated runtime
    context and a genuine, fresh Android Driver proof callback. Neither
    comes from a workflow payload or CLI flag.
    """
    _require(_GATEWAY_PUBLISHER_EXECUTION_ACCEPTED,
             "GATEWAY_PUBLISHER_RELEASE_GATE_CLOSED")
    _require(isinstance(trusted_runtime_context, Mapping),
             "TRUSTED_GATEWAY_RUNTIME_NOT_CONNECTED")
    if manifest.get("publish_mode") == "COMMIT":
        _require(callable(trusted_effect_callback),
                 "TRUSTED_EFFECT_AUTHORITY_NOT_CONNECTED")
    context = _verify_preexisting_context(
        publisher_job=publisher_job, manifest=manifest,
        provided=trusted_runtime_context)
    _require(manifest.get("publish_mode") in {"DRY_RUN", "COMMIT"}
             and manifest.get("visibility", "PUBLIC") == "PUBLIC",
             "PUBLISHER_MANIFEST_MISMATCH")
    _require_existing_unlocked_screen()

    # Import existing Publisher helpers lazily: no second publishing engine.
    from publisher import publish_job as old
    from apps.tiktok import controller as generic_tiktok

    metadata = old.load_metadata(publisher_job, manifest)
    visibility = str(
        metadata.get("visibility", manifest.get("visibility", "PUBLIC"))
    ).upper()
    _require(visibility == "PUBLIC", "VISIBILITY_CONTRACT_MISMATCH")
    caption = old.read_text(publisher_job / manifest["caption_file"])
    _require(bool(caption), "CAPTION_UNAVAILABLE")
    _require(not old.find_published_duplicate(
        context.publisher_job_id, metadata, manifest),
        "DUPLICATE_AWEME")
    mode = manifest["publish_mode"]

    with generic_tiktok.capability_ui_claim_scope(
        trusted_resource_guard=context.resource_guard(),
        capability_job_id=context.capability_job_id,
        backend_job_id=context.backend_job_id,
        request_sha256=context.request_sha256,
    ):
        # The screen must already be unlocked. Preflight and MediaStore staging
        # are existing helpers, no Legacy secure_unlock/second claim.
        old.update("PREFLIGHT", context.publisher_job_id,
                   publisher_mode="CAPABILITY",
                   capability_job_id=context.capability_job_id)
        old.run([str(old.PREFLIGHT), "--gateway-readonly"])
        old.update("STAGING", context.publisher_job_id,
                   publisher_mode="CAPABILITY")
        old.run([str(old.sys.executable), str(old.STAGER),
                 context.publisher_job_id, "--gateway-bound"])
        resource_arbiter.assert_guard(context.resource_guard())

        if mode == "DRY_RUN":
            # A preview must NEVER leave an unattended account on the
            # final Publish screen. Force-stop via the existing Core while
            # still inheriting the SAME canonical Capability claim.
            # A cleanup failure is UNKNOWN rather than a verified DRY_RUN.
            try:
                ready = generic_tiktok.prepare_dry_run(
                    caption, title=str(metadata.get("title", "")),
                    visibility=visibility, album="Y700Agent")
                _require(isinstance(ready.get("ui_state"), Mapping)
                         and ready["ui_state"].get("state") == "POST_CONFIG"
                         and ready.get("caption_verified") is True
                         and ready.get("visibility") == "PUBLIC",
                         "DRY_RUN_POSTCONFIG_NOT_VERIFIED")
                evidence = old.store_generic_evidence(publisher_job, ready)
                old.update("READY_TO_COMMIT", context.publisher_job_id,
                           publisher_mode="CAPABILITY", evidence=evidence,
                           workflow_job_id=ready["workflow_job_id"])
            finally:
                # No COMMIT callback, approval consumption or one-click
                # attempt can occur in this branch. A failed cleanup is
                # explicit reconcile-required, never a verified preview.
                try:
                    generic_tiktok.force_stop()
                except Exception:
                    try:
                        old.update(
                            "DRY_RUN_RECONCILE_REQUIRED",
                            context.publisher_job_id,
                            publisher_mode="CAPABILITY",
                            capability_job_id=context.capability_job_id,
                            ui_cleanup_complete=False,
                            external_effect_attempts=0,
                            retry_allowed=False,
                        )
                    except Exception:
                        # Retain the original UI cleanup failure as the
                        # primary error. The Capability claim remains held
                        # for exact resource-only reconciliation.
                        pass
                    raise
            resource_arbiter.assert_guard(context.resource_guard())
            old.update("DRY_RUN_COMPLETE", context.publisher_job_id,
                       publisher_mode="CAPABILITY",
                       capability_job_id=context.capability_job_id,
                       evidence=evidence,
                       ui_cleanup_complete=True,
                       external_effect_attempts=0)
            return {
                "status": "DRY_RUN_READY_ONLY",
                "capability_job_id": context.capability_job_id,
                "backend_job_id": context.backend_job_id,
                "publisher_job_id": context.publisher_job_id,
                "request_sha256": context.request_sha256,
                "content_sha256": context.content_sha256,
                "caption_sha256": context.caption_sha256,
                "ui_cleanup_complete": True,
                "external_effect_attempts": 0,
                "result": ready,
            }

        _require(mode == "COMMIT", "PUBLISHER_MODE_UNSUPPORTED")
        # The trusted callback must itself cross the exact durable
        # capability boundary with approval/epoch/revision/claim checks.
        # Its returned receipt is NEVER evidence by itself that the Android
        # Driver has been accepted. The native input gate is independent.
        effect_started = False
        success_receipt_durable = False

        def before_irreversible() -> None:
            nonlocal effect_started
            resource_arbiter.assert_guard(context.resource_guard())
            # Pin video/caption bytes against the immutable manifest and
            # Gateway binding BEFORE consuming a one-use public approval.
            # This does not replace the second just-in-time verification
            # after the durable effect boundary and before the one click.
            verify_before_publisher_committing(
                job=publisher_job, manifest=manifest,
                gateway_binding=binding)
            old.update("READY_TO_COMMIT", context.publisher_job_id,
                       publisher_mode="CAPABILITY")
            _require(callable(trusted_effect_callback),
                     "TRUSTED_EFFECT_AUTHORITY_NOT_CONNECTED")
            receipt = trusted_effect_callback()
            # The callback's returned dictionary is not durable authority.
            # Reopen the exact root-owned effect record and pin every
            # immutable identity before entering Publisher COMMITTING.
            boundary_path = (Path("/opt/y700/capability-jobs/active")
                             / context.capability_job_id / "effect-boundary.json")
            _require(not boundary_path.is_symlink() and boundary_path.is_file(),
                     "EFFECT_BOUNDARY_DURABLE_PROOF_UNAVAILABLE")
            try:
                durable = _read_json(boundary_path)
            except (OSError, ValueError, CapabilityStoreError) as exc:
                raise GatewayPublisherUnavailable(
                    "EFFECT_BOUNDARY_DURABLE_PROOF_UNAVAILABLE") from exc
            expected = {
                "phase": "EFFECT_BOUNDARY_CROSSED",
                "capability": "tiktok.publish",
                "capability_job_id": context.capability_job_id,
                "backend_job_id": context.backend_job_id,
                "request_sha256": context.request_sha256,
                "effective_policy_sha256": context.effective_policy_sha256,
                "content_sha256": context.content_sha256,
                "visibility": "PUBLIC",
            }
            # cross_effect_boundary returns a deliberately minimal ACK;
            # immutable content/policy identity lives in its fsynced
            # effect-boundary.json, not in the callback return value.
            callback_expected = {
                "effect_boundary_version": 1,
                "phase": "EFFECT_BOUNDARY_CROSSED",
                "capability_job_id": context.capability_job_id,
                "backend_job_id": context.backend_job_id,
                "production_dispatch_authorized": False,
                "effect_attempts_performed_by_this_module": 0,
            }
            _require(isinstance(receipt, Mapping)
                     and all(receipt.get(k) == v
                             for k, v in callback_expected.items())
                     and all(durable.get(k) == v for k, v in expected.items())
                     and durable.get("effect_boundary_version") == 1
                     and durable.get("boundary") == "before_final_publish"
                     and durable.get("external_effect_attempts_allowed") == 1
                     and durable.get("external_effect_attempts_observed") == 0,
                     "EFFECT_BOUNDARY_RECEIPT_MISMATCH")
            approval_path = (Path("/opt/y700/capability-jobs/active")
                             / context.capability_job_id / "approval.json")
            _require(not approval_path.is_symlink()
                     and approval_path.is_file(),
                     "PUBLISHER_APPROVAL_DURABLE_PROOF_UNAVAILABLE")
            try:
                approval = _read_json(approval_path)
            except (OSError, ValueError, CapabilityStoreError) as exc:
                raise GatewayPublisherUnavailable(
                    "PUBLISHER_APPROVAL_DURABLE_PROOF_UNAVAILABLE") from exc
            _require(_sha(approval) == durable.get("approval_sha256")
                     and approval.get("job_id") == context.capability_job_id
                     and approval.get("request_sha256")
                         == context.request_sha256
                     and approval.get("effective_policy_sha256")
                         == context.effective_policy_sha256
                     and approval.get("content_sha256")
                         == context.content_sha256
                     and approval.get("caption_sha256")
                         == context.caption_sha256
                     and approval.get("visibility") == "PUBLIC"
                     and approval.get("approval_id")
                         == durable.get("approval_id")
                     and approval.get("approval_nonce")
                         == durable.get("approval_nonce")
                     and approval.get("single_use") is True,
                     "PUBLISHER_APPROVAL_EFFECT_IDENTITY_MISMATCH")
            verify_before_publisher_committing(
                job=publisher_job, manifest=manifest,
                gateway_binding=binding)
            # Upper durable effect boundary first; backend-specific
            # COMMITTING is fsynced by Publisher's existing write helper
            # before a single controller external click.
            old.update("COMMITTING", context.publisher_job_id,
                       publisher_mode="CAPABILITY",
                       capability_job_id=context.capability_job_id,
                       retry_allowed=False)
            effect_started = True

        try:
            ready = generic_tiktok.commit_public(
                caption, title=str(metadata.get("title", "")),
                visibility=visibility, album="Y700Agent",
                before_irreversible=before_irreversible,
                capability_bound=True,
            )
            evidence = old.store_generic_evidence(publisher_job, ready)
            verification = old.verify_public_post(publisher_job, caption)
            _require(isinstance(verification, Mapping)
                     and verification.get("verified") is True,
                     "PUBLISHER_PROFILE_VERIFICATION_UNPROVEN")
            # Reuse the original Publisher's success archive. Never
            # overwrite an existing published job, which could hide a
            # duplicate external effect after a crash/retry.
            old.PUBLISHED.mkdir(parents=True, exist_ok=True)
            dest = old.PUBLISHED / context.publisher_job_id
            _require(not dest.exists() and not dest.is_symlink(),
                     "PUBLISHER_ALREADY_ARCHIVED")
            result = {
                "status": "PUBLISHED",
                "job_id": context.publisher_job_id,
                "capability_job_id": context.capability_job_id,
                "backend_job_id": context.backend_job_id,
                "request_sha256": context.request_sha256,
                "content_sha256": context.content_sha256,
                "caption_sha256": context.caption_sha256,
                "visibility": "PUBLIC",
                "external_effect_retry_allowed": False,
                "verification": verification,
                "ready": {
                    "commit_workflow_job_id":
                        ready.get("commit_workflow_job_id"),
                    "commit_preflight_workflow_job_id":
                        ready.get("commit_preflight_workflow_job_id"),
                },
            }
            # Durable positive Profile receipt FIRST, then the namespace
            # rename. A crash between these phases preserves verification
            # under ready/ for explicit archive reconciliation; the original
            # Publisher must NEVER execute again using this same identity.
            old.write_json_atomic(
                publisher_job / "publish-result.json", result)
            success_receipt_durable = True
            old.update("PUBLISHED", context.publisher_job_id,
                       publisher_mode="CAPABILITY",
                       capability_job_id=context.capability_job_id,
                       verification=verification)
            publisher_job.replace(dest)
            _sync_directory(publisher_job.parent)
            _sync_directory(dest.parent)
            return {
                "status": "PROFILE_VERIFIED",
                "capability_job_id": context.capability_job_id,
                "publisher_job_id": context.publisher_job_id,
                "external_effect_retry_allowed": False,
                "ready": ready,
                "verification": verification,
                "evidence": evidence,
            }
        except Exception:
            # Boundary may have become durable even if a subsequent receipt,
            # legacy COMMITTING marker, or Python callback failed before
            # setting effect_started. Never reinterpret that as safe retry.
            cap = Path("/opt/y700/capability-jobs/active")
            boundary_won = (
                cap / context.capability_job_id / "effect-boundary.json"
            ).exists()
            if (effect_started or boundary_won) and not success_receipt_durable:
                # The global Publisher status is advisory, and failure to
                # update it may never hide the *original* post-boundary
                # failure or trigger re-creation of a ready/ job.
                try:
                    old.update("AMBIGUOUS_COMMIT_NEEDS_RECONCILE",
                               context.publisher_job_id,
                               publisher_mode="CAPABILITY",
                               retry_allowed=False)
                except Exception:
                    # The durable effect-boundary/job evidence remains SOT.
                    # The original exception still propagates unchanged.
                    pass
            # Positive Profile receipt (if already fsynced) is never
            # overwritten by an 'ambiguous' marker, even when its final
            # archive rename failed. Reconcile the SAME job only.
            raise
