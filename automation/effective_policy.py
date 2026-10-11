"""Rev3.7 minimum/effective policy resolution and strict request admission.

Catalog policy defines the security floor. Trusted operator restrictions may
tighten, NEVER relax it; workflow JSON fields are data, not policy authority.
This module resolves policy and rejects requests but never creates a
capability job, a resource claim, or an Android/Publisher operation.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any, Mapping


class PolicyUnavailable(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _need(ok: bool, code: str) -> None:
    if not ok:
        raise PolicyUnavailable(code)


_APPROVAL_ORDER = {"NONE": 0, "REQUIRED": 1, "MAINTENANCE_ONLY": 2}
_VERIFY_ORDER = {"NONE": 0, "REQUIRED": 1, "ADMIN_EXPLICIT_UNSAFE": 2}
_REPLAY_ORDER = {"SAFE_READ_ONLY": 0, "NEVER": 1}
_SUBMISSION = re.compile(r"^[A-Za-z0-9_.-]{16,128}$")


@dataclass(frozen=True)
class EffectivePolicy:
    version: int
    replay: str
    approval: str
    verification: str
    max_ttl_sec: int
    classification: str
    y700_required: bool
    resource: str | None
    alternate_runtime_fallback: str = "NONE"

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "replay": self.replay,
            "approval": self.approval,
            "verification": self.verification,
            "max_ttl_sec": self.max_ttl_sec,
            "classification": self.classification,
            "runtime": "Y700",
            "resource": self.resource,
            "alternate_runtime_fallback":
                self.alternate_runtime_fallback,
            "approved_for_production": False,
        }


def _choice(source: Mapping[str, Any], key: str,
            allowed: dict[str, int], fallback: str) -> str:
    value = source.get(key, fallback)
    _need(value in allowed, "POLICY_CONTRACT_INVALID")
    return value


def resolve_effective_policy(
    capability: Mapping[str, Any], *,
    trusted_operator_restrictions: Mapping[str, Any] | None = None,
) -> EffectivePolicy:
    """Minimum + stricter operator rules, never caller-defined overrides."""
    _need(isinstance(capability, Mapping), "CAPABILITY_CATALOG_INVALID")
    minimum = capability.get("minimum_policy")
    _need(isinstance(minimum, Mapping), "CAPABILITY_CATALOG_INVALID")
    operator = (trusted_operator_restrictions
                if trusted_operator_restrictions is not None else {})
    _need(isinstance(operator, Mapping), "POLICY_UNRESOLVED")
    base_replay = _choice(minimum, "replay", _REPLAY_ORDER, "NEVER")
    base_approval = _choice(
        minimum, "approval", _APPROVAL_ORDER, "REQUIRED")
    base_verify = _choice(
        minimum, "verification", _VERIFY_ORDER, "REQUIRED")
    replay = _choice(operator, "replay", _REPLAY_ORDER, base_replay)
    approval = _choice(
        operator, "approval", _APPROVAL_ORDER, base_approval)
    verification = _choice(
        operator, "verification", _VERIFY_ORDER, base_verify)
    _need(_REPLAY_ORDER[replay] >= _REPLAY_ORDER[base_replay]
          and _APPROVAL_ORDER[approval] >= _APPROVAL_ORDER[base_approval]
          and _VERIFY_ORDER[verification] >= _VERIFY_ORDER[base_verify],
          "POLICY_WEAKENING_DENIED")
    max_ttl = minimum.get("expires_in_max_sec")
    _need(type(max_ttl) is int and 0 < max_ttl <= 86400,
          "POLICY_CONTRACT_INVALID")
    override_max = operator.get("max_ttl_sec", max_ttl)
    _need(type(override_max) is int and 0 < override_max <= max_ttl,
          "POLICY_WEAKENING_DENIED")
    profile = capability.get("execution_profile")
    _need(isinstance(profile, Mapping)
          and profile.get("placement") == "Y700_REQUIRED"
          and profile.get("alternate_runtime_fallback") == "NONE",
          "EXECUTION_PROFILE_INVALID")
    return EffectivePolicy(
        version=1,
        replay=replay,
        approval=approval,
        verification=verification,
        max_ttl_sec=override_max,
        classification=capability.get("classification", "UNKNOWN"),
        y700_required=True,
        resource=capability.get("resource"),
    )


def check_request_contract(
    *,
    request: Mapping[str, Any],
    capability: Mapping[str, Any],
    effective: EffectivePolicy,
    trusted_authenticated_identity: bool,
) -> dict[str, Any]:
    """Reject stale/forged input before any durable admission or execution."""
    if not isinstance(request, Mapping):
        raise PolicyUnavailable("CAPABILITY_REQUEST_INVALID")
    if trusted_authenticated_identity is not True:
        raise PolicyUnavailable("PERMISSION_DENIED")
    if capability.get("enabled") is not True:
        raise PolicyUnavailable("CAPABILITY_CONTRACT_DISABLED")
    submission = request.get("submission_id")
    if (not isinstance(submission, str)
            or _SUBMISSION.fullmatch(submission) is None):
        raise PolicyUnavailable("SUBMISSION_ID_INVALID")
    if (request.get("capability") != capability.get("name")
            or request.get("version") != capability.get("version")):
        raise PolicyUnavailable("CAPABILITY_VERSION_MISMATCH")
    if not isinstance(request.get("payload"), Mapping):
        raise PolicyUnavailable("JOB_PAYLOAD_INVALID")
    for forbidden in (
        "resource", "resources", "policy", "approval", "verification",
        "replay", "backend_job_id", "route", "effective_policy",
        "resource_guard", "approval_consumed",
    ):
        if forbidden in request:
            raise PolicyUnavailable("CALLER_POLICY_OVERRIDE_DENIED")
    if effective.classification == "BUSINESS":
        if (effective.approval != "REQUIRED"
                or effective.verification != "REQUIRED"
                or effective.replay != "NEVER"):
            raise PolicyUnavailable("BUSINESS_MINIMUM_POLICY_INVALID")
    deadline = request.get("expires_at")
    if deadline is not None:
        if not isinstance(deadline, str):
            raise PolicyUnavailable("TTL_INVALID")
        try:
            instant = datetime.fromisoformat(
                deadline.replace("Z", "+00:00"))
        except ValueError as exc:
            raise PolicyUnavailable("TTL_INVALID") from exc
        if instant.tzinfo is None:
            raise PolicyUnavailable("TTL_INVALID")
    return {
        "status": "CONTRACT_VERIFIED_READ_ONLY",
        "effective_policy": effective.as_dict(),
        "request_identity_valid": True,
        "execution_authorized": False,
        "backend_submitted": False,
        "ui_mutation_attempts": 0,
    }
