"""Rev3.7 Y700 local fixed backend registry: FOUR capabilities, no plugins.

Strictly in-process and foreground only. Every backend is bound to its
ONE deterministic ID and the current admitted job's durable identity.
No background scheduling, alternate runtime, or automatic effect replay.

All execution release gates stay FALSE throughout the development batch;
these adapters are candidates for later final acceptance, not live paths.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping
import re

from automation.capability_job_store import (
    AdmittedJob, CapabilityStore, CapabilityStoreError, _need, _read_json,
    _sha,
)
from automation.gateway_adapters import (
    AdapterContractError, prepare_adapter_intent_readonly,
)
from automation.authoritative_state_reader import observe_authoritative_state
from automation import resource_arbiter
from automation.publisher_backend_adapter import LocalPublisherBackend

_BACKEND_TO_CAPABILITY = {
    "observation": "android.device.observe",
    "ui_workflow": "android.ui.workflow",
    "root_exec": "android.root.exec",
    "publisher": "tiktok.publish",
}
_BACKEND_SUFFIX = {
    "observation": "observe", "ui_workflow": "ui",
    "root_exec": "root", "publisher": "publisher",
}
_OBSERVATION_EXECUTION_ACCEPTED = False
_SETTINGS_BACKEND_ACCEPTED = False
_ROOT_BACKEND_ACCEPTED = False
_ID = re.compile(r"^cap-[0-9a-f]{48}$")


class LocalBackendUnavailable(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _require(ok: bool, code: str) -> None:
    if not ok:
        raise LocalBackendUnavailable(code)


@dataclass(frozen=True)
class FixedBackendJob:
    admitted: AdmittedJob
    backend_type: str
    backend_job_id: str

    @property
    def capability(self) -> str:
        return _BACKEND_TO_CAPABILITY[self.backend_type]


class LocalFixedBackend:
    """Fixed adapter shell; publisher delegates to original Publisher."""

    def __init__(self, *,
                 store: CapabilityStore | None = None,
                 publisher: LocalPublisherBackend | None = None):
        self.store = store or CapabilityStore()
        self.publisher = publisher or LocalPublisherBackend(store=self.store)

    def _get(self, backend_type: str, backend_id: str) -> FixedBackendJob:
        _require(backend_type in _BACKEND_SUFFIX,
                 "BACKEND_TYPE_NOT_REGISTERED")
        suffix = "--" + _BACKEND_SUFFIX[backend_type] + "-01"
        _require(isinstance(backend_id, str)
                 and backend_id.endswith(suffix),
                 "BACKEND_IDENTITY_INVALID")
        cap_id = backend_id[:-len(suffix)]
        _require(bool(_ID.fullmatch(cap_id)),
                 "CAPABILITY_JOB_ID_INVALID")
        source = self.store.jobs / "active" / cap_id
        _require(source.is_dir() and not source.is_symlink(),
                 "CAPABILITY_JOB_UNAVAILABLE")
        ident = _read_json(source / "identity.json")
        record = _read_json(source / "backend.json")
        request = _read_json(source / "request.json")
        _require(record.get("backend_job_id") == backend_id
                 and record.get("backend_type") == backend_type
                 and record.get("capability_job_id") == cap_id
                 and ident.get("capability_job_id") == cap_id
                 and record.get("request_sha256")
                     == ident.get("request_sha256")
                 and _sha(request) == ident.get("request_sha256")
                 and request.get("capability")
                     == _BACKEND_TO_CAPABILITY[backend_type],
                 "BACKEND_IDENTITY_MISMATCH")
        return FixedBackendJob(
            AdmittedJob(cap_id, source, ident["request_sha256"],
                        ident["effective_policy_sha256"], False),
            backend_type, backend_id,
        )

    def _assert_exact_intent(self, job: FixedBackendJob,
                             intent: Mapping[str, Any]) -> None:
        """Reconstruct the adapter from durable request, never caller data."""
        _require(isinstance(intent, Mapping)
                 and intent.get("backend_job_id") == job.backend_job_id
                 and intent.get("capability_job_id") == job.admitted.job_id
                 and intent.get("request_sha256")
                     == job.admitted.request_sha256
                 and intent.get("effective_policy_sha256")
                     == job.admitted.effective_policy_sha256,
                 "BACKEND_INTENT_IDENTITY_MISMATCH")
        request = _read_json(job.admitted.path / "request.json")
        policy = _read_json(job.admitted.path / "effective_policy.json")
        _require(_sha(request) == job.admitted.request_sha256
                 and _sha(policy) == job.admitted.effective_policy_sha256,
                 "BACKEND_DURABLE_REQUEST_DRIFT")
        try:
            expected = prepare_adapter_intent_readonly(
                capability=job.capability,
                immutable_payload=request.get("payload"),
                exact_backend_id=job.backend_job_id,
                exact_request_sha256=job.admitted.request_sha256,
            )
        except (AdapterContractError, TypeError, ValueError) as exc:
            raise LocalBackendUnavailable(
                "BACKEND_DURABLE_ADAPTER_INVALID") from exc
        _require(isinstance(intent.get("adapter_intent"), Mapping)
                 and dict(intent["adapter_intent"]) == expected,
                 "BACKEND_ADAPTER_CONTRACT_MISMATCH")

    def lookup_exact(self, backend_type: str,
                     backend_id: str) -> dict[str, Any]:
        if backend_type == "publisher":
            return self.publisher.lookup_exact(backend_type, backend_id)
        job = self._get(backend_type, backend_id)
        from automation.capability_job_store import _locked
        with _locked(job.admitted.path / "transition.lock", shared=True):
            execution = _read_json(
                job.admitted.path / "backend-execution.json")
            state = _read_json(job.admitted.path / "state.json")
            _require(execution.get("backend_job_id") == backend_id
                     and execution.get("request_sha256")
                         == job.admitted.request_sha256,
                     "BACKEND_WITNESS_IDENTITY_MISMATCH")
            never = (
                execution.get("phase") == "NEVER_CREATED"
                and execution.get("attempt_serial") == 0
                and execution.get("submission_possible") is False
                and state.get("backend_submitted") is False
                and state.get("mutation_uncertain") is False
                and not (job.admitted.path / "result.json").exists()
            )
            return {
                "exists": not never,
                "durable_never_created_proof": never,
                "backend_job_id": backend_id,
                "request_sha256": job.admitted.request_sha256,
                "backend_phase": execution.get("phase", "UNKNOWN"),
                "external_effect_retry_allowed": False,
            }

    def prepare_exact(self, backend_type: str, backend_id: str,
                      intent: Mapping[str, Any]) -> dict[str, Any]:
        if backend_type == "publisher":
            return self.publisher.prepare_exact(
                backend_type, backend_id, intent)
        job = self._get(backend_type, backend_id)
        self._assert_exact_intent(job, intent)
        adapter = intent["adapter_intent"]
        needs_ui = backend_type == "ui_workflow"
        _require((isinstance(intent.get("resource_guard"), Mapping))
                 is needs_ui, "BACKEND_RESOURCE_CONTRACT_MISMATCH")
        if needs_ui:
            from automation import resource_arbiter
            try:
                claim = resource_arbiter.assert_guard(
                    dict(intent["resource_guard"]))
            except resource_arbiter.ResourceError as exc:
                raise LocalBackendUnavailable(
                    "STALE_RESOURCE_OWNERSHIP") from exc
            _require(claim.get("capability_job_id") == job.admitted.job_id
                     and claim.get("backend_job_id") == backend_id
                     and claim.get("request_sha256")
                         == job.admitted.request_sha256,
                     "BACKEND_RESOURCE_IDENTITY_MISMATCH")
        payload = adapter.get("payload")
        _require(isinstance(payload, Mapping),
                 "BACKEND_PAYLOAD_INVALID")
        if backend_type == "ui_workflow":
            _require(payload.get("workflow_contract_id")
                     == "settings.light-dark.v1",
                     "WORKFLOW_NOT_REGISTERED")
        if backend_type == "root_exec":
            _require(payload.get("maintenance_contract_id")
                     == "read-only-system-info.v1",
                     "ROOT_COMMAND_NOT_REGISTERED")
        if backend_type == "observation":
            _require(payload.get("observer_version") == 1,
                     "OBSERVATION_VERSION_MISMATCH")
        return {
            "prepared": True,
            "backend_job_id": backend_id,
            "request_sha256": job.admitted.request_sha256,
            "backend_state_mutated": False,
            "external_effect_attempts": 0,
        }

    def submit_exact(self, backend_type: str, backend_id: str,
                     intent: Mapping[str, Any]) -> dict[str, Any]:
        """Submission begins ONLY after durable SUBMISSION_POSSIBLE."""
        if backend_type == "publisher":
            return self.publisher.submit_exact(
                backend_type, backend_id, intent)
        job = self._get(backend_type, backend_id)
        self._assert_exact_intent(job, intent)
        phase = _read_json(
            job.admitted.path / "backend-execution.json")
        _require(phase.get("phase") == "SUBMISSION_POSSIBLE"
                 and phase.get("submission_possible") is True
                 and phase.get("attempt_serial") == 1
                 and phase.get("backend_job_id") == backend_id
                 and phase.get("capability_job_id") == job.admitted.job_id
                 and phase.get("request_sha256")
                     == job.admitted.request_sha256
                 and not (job.admitted.path / "result.json").exists()
                 and not (job.admitted.path / "effect-boundary.json").exists(),
                 "BACKEND_SUBMIT_WITNESS_INVALID")

        # These are release-authorized source decisions, not request flags.
        if backend_type == "observation":
            _require(_OBSERVATION_EXECUTION_ACCEPTED,
                     "OBSERVATION_BACKEND_GATE_CLOSED")
            # A safe observation reads SOT and never asks for android_ui.
            fact = observe_authoritative_state()
            self.store.record_backend_submission(
                job.admitted, exact_backend_job_id=backend_id,
                backend_identity_confirmed=True)
            from automation.capability_job_store import _atomic_new, _locked
            with _locked(job.admitted.path / "transition.lock"):
                _atomic_new(job.admitted.path / "observation-result.json", {
                    "observation_result_version": 1,
                    "capability_job_id": job.admitted.job_id,
                    "backend_job_id": backend_id,
                    "request_sha256": job.admitted.request_sha256,
                    "authoritative_state_observed": True,
                    "read_only": True,
                })
            return {
                "accepted": True,
                "backend_job_id": backend_id,
                "request_sha256": job.admitted.request_sha256,
                "read_only_authority": fact.safe_receipt(),
                "backend_synchronous_complete": True,
                "ui_mutators_quiesced_positive": True,
            }

        if backend_type == "ui_workflow":
            _require(_SETTINGS_BACKEND_ACCEPTED,
                     "SETTINGS_BACKEND_GATE_CLOSED")
            from automation.settings_golden_adapter import (
                execute_settings_golden,
            )
            self.store.record_backend_submission(
                job.admitted, exact_backend_job_id=backend_id,
                backend_identity_confirmed=True)
            receipt = execute_settings_golden(
                job.admitted, backend_job_id=backend_id,
                current_resource_guard=intent["resource_guard"],
                device_contract="y700-android16-zui")
            _require(receipt.get("status") == "VERIFIED"
                     and receipt.get("initial_mode")
                         == receipt.get("restored_mode"),
                     "SETTINGS_RESTORE_UNVERIFIED")
            from automation.resource_stop_observer import (
                positive_synchronous_ui_quiescence,
            )
            from automation.native_stop_receipt_producer import (
                NativeStopReceiptUnavailable,
                publish_generation_bound_stop_receipt,
            )
            # Settings restoration correctness and UI resource quiescence
            # are separate. The physical Native/Bridge producer is asked
            # for an exact current-generation receipt; an unavailable
            # producer NEVER becomes a successful stop assertion.
            try:
                publish_generation_bound_stop_receipt(
                    exact_claim=intent["resource_guard"],
                    backend_job_id=backend_id)
            except (NativeStopReceiptUnavailable,
                    resource_arbiter.ResourceError):
                pass
            stopped = positive_synchronous_ui_quiescence(
                intent["resource_guard"], backend_job_id=backend_id)
            return {
                "accepted": True,
                "backend_job_id": backend_id,
                "request_sha256": job.admitted.request_sha256,
                "ui_mutators_quiesced_positive": stopped,
                "settings_golden": receipt,
                "external_effect_retry_allowed": False,
            }

        _require(backend_type == "root_exec",
                 "BACKEND_TYPE_NOT_REGISTERED")
        _require(_ROOT_BACKEND_ACCEPTED,
                 "ROOT_BACKEND_GATE_CLOSED")
        # Unknown state effect: bump epoch before any privileged execution.
        # This uses ONLY the existing Bridge root-exec wrapper, never an
        # alternate root executor, caller shell, or requested command path.
        adapter = intent.get("adapter_intent")
        payload = adapter.get("payload") if isinstance(adapter, Mapping) else None
        _require(isinstance(payload, Mapping)
                 and payload.get("maintenance_contract_id")
                     == "read-only-system-info.v1",
                 "ROOT_COMMAND_NOT_REGISTERED")
        # Persist the single submission BEFORE touching state_epoch.
        # A crash after this point is reconcile-only, never a second root
        # invocation; epoch must still advance before the root command.
        self.store.record_backend_submission(
            job.admitted, exact_backend_job_id=backend_id,
            backend_identity_confirmed=True)
        from automation import state_integrity
        state_integrity.bump_epoch(
            "CAPABILITY_ROOT_EXEC_UNKNOWN_STATE:" + backend_id)
        import subprocess
        script = Path(__file__).resolve().parents[1] / "bridge/root-exec.sh"
        _require(script.is_file() and not script.is_symlink(),
                 "ROOT_BRIDGE_UNAVAILABLE")
        # Every character is a source-defined literal, not the model/CLI.
        try:
            observation = subprocess.run(
                [str(script),
                 "getprop ro.product.model; getprop ro.build.version.release"],
                capture_output=True, text=True, check=False, timeout=20,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise LocalBackendUnavailable(
                "ROOT_EXECUTION_RECONCILE_REQUIRED") from exc
        if observation.returncode != 0:
            raise LocalBackendUnavailable(
                "ROOT_EXECUTION_RECONCILE_REQUIRED")
        lines = observation.stdout.splitlines()
        _require(len(lines) >= 2
                 and all(0 < len(item) <= 128
                         and chr(0) not in item for item in lines[:2]),
                 "ROOT_OBSERVATION_UNRELIABLE")
        from automation.capability_job_store import _atomic_new, _locked
        with _locked(job.admitted.path / "transition.lock"):
            _atomic_new(job.admitted.path / "root-result.json", {
                "root_result_version": 1,
                "capability_job_id": job.admitted.job_id,
                "backend_job_id": backend_id,
                "request_sha256": job.admitted.request_sha256,
                "fixed_maintenance_contract_id": "read-only-system-info.v1",
                "root_epoch_advanced": True,
                "command_exited_zero": True,
            })
        return {
            "accepted": True,
            "backend_job_id": backend_id,
            "request_sha256": job.admitted.request_sha256,
            "fixed_maintenance_contract_id": "read-only-system-info.v1",
            "root_epoch_advanced": True,
            "device_model_observed": True,
            "android_version_observed": True,
            "external_effect_retry_allowed": False,
            "ui_mutators_quiesced_positive": True,
        }
