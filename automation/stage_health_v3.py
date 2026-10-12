"""Rev3.7 stage diagnostics v3: on-demand advisory view, never authority.

Every stage has its own observation time/boot/reason. Connectivity PASS
cannot imply frame, dispatch, postcondition, or BUSINESS outcome PASS.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

STAGES = (
    "control_plane", "device_connectivity", "observation_source",
    "frame_acquisition", "frame_freshness", "target_localization",
    "permission", "resource_ownership", "state_guard", "action_dispatch",
    "postcondition", "business_verification",
)


class StageState(str, Enum):
    UNKNOWN = "UNKNOWN"
    PASS = "PASS"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    FAIL = "FAIL"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class StageEvidenceInvalid(ValueError):
    pass


@dataclass(frozen=True)
class StageEvidence:
    stage: str
    state: StageState
    boot_id: str | None
    boottime_ms: int | None
    reason_codes: tuple[str, ...] = ()

    def normalized(self, current_boot: str, now_ms: int,
                   freshness_ms: int | None) -> "StageEvidence":
        if (type(freshness_ms) is not int or freshness_ms <= 0
                or freshness_ms > 60000 or self.boot_id != current_boot
                or type(self.boottime_ms) is not int
                or self.boottime_ms < 0 or self.boottime_ms > now_ms
                or now_ms - self.boottime_ms > freshness_ms):
            return StageEvidence(
                self.stage, StageState.UNKNOWN, None, None,
                ("STAGE_STALE_OR_BOOT_CHANGED",),
            )
        return self

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.state.value,
            "reason_codes": list(self.reason_codes),
            "observed_boot_id": self.boot_id,
            "observed_boottime_ms": self.boottime_ms,
        }


def stage_evidence(
    stage: str, status: str, *, boot_id: str | None,
    boottime_ms: int | None, reason_codes: tuple[str, ...] = (),
) -> StageEvidence:
    if stage not in STAGES:
        raise StageEvidenceInvalid("STAGE_UNKNOWN")
    try:
        state = StageState(status)
    except ValueError as exc:
        raise StageEvidenceInvalid("STAGE_STATUS_UNKNOWN") from exc
    # N/A still needs fresh provenance; stale N/A must not mask
    # an unobserved or now-applicable execution stage.
    if (not isinstance(boot_id, str) or not boot_id
            or type(boottime_ms) is not int or boottime_ms < 0):
        raise StageEvidenceInvalid("STAGE_PROVENANCE_MISSING")
    if (type(reason_codes) is not tuple
            or any(type(x) is not str or not x or len(x) > 128
                   for x in reason_codes)):
        raise StageEvidenceInvalid("STAGE_REASON_INVALID")
    return StageEvidence(stage, state, boot_id, boottime_ms, reason_codes)


def on_demand_health_view(
    *, current_boot_id: str, now_boottime_ms: int,
    facts: Mapping[str, StageEvidence],
    freshness_policy_ms: Mapping[str, int],
) -> dict[str, Any]:
    """Pure formatter; neither a health daemon nor a mutation permission."""
    if (not isinstance(current_boot_id, str) or not current_boot_id
            or type(now_boottime_ms) is not int or now_boottime_ms < 0
            or not isinstance(facts, Mapping)
            or not isinstance(freshness_policy_ms, Mapping)):
        raise StageEvidenceInvalid("HEALTH_VIEW_INVALID")
    # Do not silently discard unrecognized evidence or freshness policies:
    # an incorrectly named stage must not look like an absent optional stage.
    if any(name not in STAGES for name in facts):
        raise StageEvidenceInvalid("HEALTH_STAGE_UNKNOWN")
    if any(name not in STAGES for name in freshness_policy_ms):
        raise StageEvidenceInvalid("HEALTH_FRESHNESS_STAGE_UNKNOWN")
    stages: dict[str, dict[str, Any]] = {}
    for name in STAGES:
        value = facts.get(name)
        if value is None:
            value = StageEvidence(
                name, StageState.UNKNOWN, None, None,
                ("STAGE_NOT_OBSERVED",))
        if not isinstance(value, StageEvidence) or value.stage != name:
            raise StageEvidenceInvalid("STAGE_PROVENANCE_INVALID")
        stages[name] = value.normalized(
            current_boot_id, now_boottime_ms,
            freshness_policy_ms.get(name),
        ).as_dict()

    statuses = {value["status"] for value in stages.values()
                if value["status"] != StageState.NOT_APPLICABLE.value}
    if StageState.FAIL.value in statuses:
        summary = "UNHEALTHY"
    elif StageState.BLOCKED.value in statuses:
        summary = "BLOCKED"
    elif StageState.DEGRADED.value in statuses:
        summary = "DEGRADED"
    elif StageState.UNKNOWN.value in statuses:
        summary = "UNKNOWN"
    elif statuses == {StageState.PASS.value}:
        summary = "HEALTHY"
    else:
        summary = "UNKNOWN"
    return {
        "schema_version": 3,
        "status": summary,
        "updated_boottime_ms": now_boottime_ms,
        "observed_boot_id": current_boot_id,
        "stages": stages,
        "advisory_only": True,
        "execution_authorized": False,
        "effect_outcome_authoritative": False,
    }
