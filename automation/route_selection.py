"""Rev3.7 deterministic, contract-owned local route selection.

This is a foundation function, not an alternate runtime scheduler and not a
switch that authorizes visual mutations. D-G3 remains an external blocking gate.
"""
from __future__ import annotations

from typing import Any, Mapping

ROUTE_CLASSES = frozenset({
    "VERIFIED_NOOP", "SEMANTIC_UI", "VISION_ASSISTED_UI",
    "HOST_PRIMITIVE", "BLOCKED",
})


class RouteContractError(ValueError):
    pass


def select_execution_route(
    *,
    contract: Mapping[str, Any],
    target_state: str,
    device_contract: str,
    evidence_revision: int,
    target_proven: bool,
    semantic_resolved: bool,
    vision_guard_passed: bool,
    host_primitive_ready: bool,
    action_class: str = "LOCAL_UI_MUTATION",
    dg3_accepted: bool = False,
    vision_attempted: bool = False,
) -> dict[str, Any]:
    """Return a frozen-schema route; evidence flags are trusted internal facts.

    `contract` is the static versioned adapter route table, never a caller
    override. No alternate route can silently replay an uncertain effect.
    """
    if not isinstance(contract, Mapping) or contract.get("route_version") != 1:
        raise RouteContractError("RUNTIME_CONTRACT_MISMATCH")
    routes = contract.get("route_ids")
    if not isinstance(routes, Mapping) or set(routes) != ROUTE_CLASSES:
        raise RouteContractError("RUNTIME_CONTRACT_MISMATCH")
    if any(not isinstance(v, str) or not v for v in routes.values()):
        raise RouteContractError("RUNTIME_CONTRACT_MISMATCH")
    if (
        not isinstance(target_state, str) or not target_state
        or not isinstance(device_contract, str) or not device_contract
        or type(evidence_revision) is not int or evidence_revision < 0
        or action_class not in {"OBSERVE_ONLY", "LOCAL_UI_MUTATION", "EXTERNAL_IRREVERSIBLE"}
    ):
        raise RouteContractError("CAPABILITY_REQUEST_INVALID")
    if any(type(v) is not bool for v in (
        target_proven, semantic_resolved, vision_guard_passed, host_primitive_ready, dg3_accepted, vision_attempted
    )):
        raise RouteContractError("CAPABILITY_REQUEST_INVALID")

    if target_proven:
        route_class = "VERIFIED_NOOP"
    elif semantic_resolved:
        route_class = "SEMANTIC_UI"
    elif (
        vision_guard_passed and dg3_accepted
        and action_class != "EXTERNAL_IRREVERSIBLE"
    ):
        route_class = "VISION_ASSISTED_UI"
    elif vision_attempted:
        # An attempted but unavailable/stale vision path must not silently
        # escape to an unrelated host primitive (unsafe transparent fallback).
        route_class = "BLOCKED"
    elif host_primitive_ready and bool(contract.get("host_primitive_allowed", False)):
        route_class = "HOST_PRIMITIVE"
    else:
        route_class = "BLOCKED"
    return {
        "route_version": 1,
        "route_id": routes[route_class],
        "route_class": route_class,
        "selected_for": {
            "target_state": target_state,
            "device_contract": device_contract,
            "evidence_revision": evidence_revision,
        },
    }
