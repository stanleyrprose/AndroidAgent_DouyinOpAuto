"""Rev3.7 trusted adapter route contracts (single-device, no scheduler).

Router only receives observation facts from a privileged runtime adapter;
caller route_id/maximum age/vision decision are never authoritative.
No target uses a visual mutation path while D-G3 is OPEN.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from automation.route_selection import (
    RouteContractError, select_execution_route,
)


@dataclass(frozen=True)
class FrozenRoute:
    capability: str
    version: str
    target_state: str
    route_ids: Mapping[str, str]
    host_primitive_allowed: bool
    allow_visual: bool
    max_frame_age_ms: int | None

    def as_contract(self) -> dict[str, Any]:
        return {
            "route_version": 1,
            "route_ids": dict(self.route_ids),
            "host_primitive_allowed": self.host_primitive_allowed,
        }


_ROUTES: dict[str, FrozenRoute] = {
    "settings.light-dark.v1": FrozenRoute(
        capability="android.ui.workflow",
        version="1.0",
        target_state="SETTINGS_APPEARANCE_MATCH",
        route_ids={
            "VERIFIED_NOOP": "settings.appearance.noop.v1",
            "SEMANTIC_UI": "settings.appearance.semantic.v1",
            "VISION_ASSISTED_UI": "settings.appearance.vision-not-approved.v1",
            "HOST_PRIMITIVE": "settings.appearance.host-not-approved.v1",
            "BLOCKED": "settings.appearance.blocked.v1",
        },
        host_primitive_allowed=False,
        allow_visual=False,
        max_frame_age_ms=None,
    ),
    "tiktok.create.v1": FrozenRoute(
        capability="tiktok.publish",
        version="1.0",
        target_state="POST_CONFIG_READY",
        route_ids={
            "VERIFIED_NOOP": "tiktok.post-config.noop.v1",
            "SEMANTIC_UI": "tiktok.post-config.semantic.v1",
            "VISION_ASSISTED_UI": "tiktok.post-config.vision-not-approved.v1",
            "HOST_PRIMITIVE": "tiktok.post-config.host-not-approved.v1",
            "BLOCKED": "tiktok.post-config.blocked.v1",
        },
        host_primitive_allowed=False,
        allow_visual=False,
        max_frame_age_ms=None,
    ),
}


def select_frozen_route_readonly(
    *,
    route_contract_id: str,
    adapter_capability: str,
    adapter_version: str,
    observed_target_state: str,
    observed_device_contract: str,
    observed_revision: int,
    already_satisfied_verified: bool,
    semantic_target_unique: bool,
    visual_target_verified: bool,
    host_primitive_ready: bool,
    action_class: str,
) -> dict[str, Any]:
    """Deterministic selection; no action or request-chosen fallback."""
    route = _ROUTES.get(route_contract_id)
    if route is None or (
        route.capability != adapter_capability
        or route.version != adapter_version
        or route.target_state != observed_target_state
    ):
        raise RouteContractError("RUNTIME_CONTRACT_MISMATCH")
    if type(observed_revision) is not int or observed_revision < 0:
        raise RouteContractError("STATE_REVISION_UNAVAILABLE")
    for value in (
        already_satisfied_verified, semantic_target_unique,
        visual_target_verified, host_primitive_ready,
    ):
        if type(value) is not bool:
            raise RouteContractError("ROUTE_EVIDENCE_MALFORMED")

    chosen = select_execution_route(
        contract=route.as_contract(),
        target_state=observed_target_state,
        device_contract=observed_device_contract,
        evidence_revision=observed_revision,
        target_proven=already_satisfied_verified,
        semantic_resolved=semantic_target_unique,
        vision_guard_passed=route.allow_visual and visual_target_verified,
        host_primitive_ready=host_primitive_ready,
        action_class=action_class,
        dg3_accepted=False,
        vision_attempted=visual_target_verified,
    )
    chosen["production_dispatch_authorized"] = False
    chosen["dg3_status"] = "OPEN"
    chosen["action_attempts"] = 0
    chosen["route_contract_id"] = route_contract_id
    return chosen
