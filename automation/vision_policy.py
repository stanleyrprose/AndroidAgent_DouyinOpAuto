"""Routing policy for the Y700 Vision Locator.

This module is deliberately NOT wired into production action dispatch during
Sprint V0.  It freezes the decision contract that V1/V3 may consume after Gate
V0 passes.  The key rule is that vision eligibility is a policy decision; the
locator itself only resolves targets.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping, Any


class SemanticStatus(str, Enum):
    RESOLVED = "RESOLVED"
    NOT_FOUND = "NOT_FOUND"
    AMBIGUOUS = "AMBIGUOUS"
    UNRELIABLE = "UNRELIABLE"


class Route(str, Enum):
    SEMANTIC = "SEMANTIC"
    VISION_TEMPLATE = "VISION_TEMPLATE"
    VISION_OCR = "VISION_OCR"
    VISION_BENCHMARK_ONLY = "VISION_BENCHMARK_ONLY"
    BLOCKED = "BLOCKED"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True)
class VisionPolicy:
    vision_enabled: bool = False
    mode: str = "benchmark_only"  # off | benchmark_only | fallback
    template_enabled: bool = True
    ocr_enabled: bool = False
    gate_v0_passed: bool = False
    gate_v2_passed: bool = False
    allow_high_risk_vision: bool = False


@dataclass(frozen=True)
class RoutingDecision:
    route: Route
    reason: str
    locator: Mapping[str, Any] | None = None
    action_authorized: bool = False
    require_exact_input: bool = False
    require_secondary_validation: bool = False


_HIGH_RISK_SIDE_EFFECTS = {"EXTERNAL_IRREVERSIBLE"}
_VISION_TYPES = {"vision_template", "vision_text"}


def _vision_candidates(selector: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    direct = selector.get("type")
    if direct in _VISION_TYPES:
        return [selector]

    templates: list[Mapping[str, Any]] = []
    ocr: list[Mapping[str, Any]] = []
    fallback = selector.get("fallback")
    if isinstance(fallback, Iterable) and not isinstance(fallback, (str, bytes, Mapping)):
        for item in fallback:
            if not isinstance(item, Mapping):
                continue
            kind = item.get("type")
            if kind == "vision_template":
                templates.append(item)
            elif kind == "vision_text":
                ocr.append(item)
    # Sprint V3 freezes the runtime order independently of caller ordering:
    # semantic -> template -> OCR.
    return [*templates, *ocr]


def decide_route(
    *,
    semantic_status: SemanticStatus | str,
    selector: Mapping[str, Any],
    side_effect: str = "NONE",
    policy: VisionPolicy = VisionPolicy(),
    secondary_validation_available: bool = False,
) -> RoutingDecision:
    """Return a fail-closed routing decision.

    Sprint V0 never authorizes a vision-derived action. In future fallback mode,
    a vision route is eligible only when the selector explicitly carries a
    vision selector/fallback. Irreversible actions remain denied by default.
    """
    status = SemanticStatus(semantic_status)

    if status is SemanticStatus.RESOLVED:
        return RoutingDecision(
            Route.SEMANTIC,
            "semantic target resolved; vision must not be invoked",
            action_authorized=True,
        )

    candidates = _vision_candidates(selector)
    if not candidates:
        return RoutingDecision(
            Route.UNRESOLVED,
            "semantic target unresolved and selector has no explicit vision fallback",
        )

    if not policy.vision_enabled or policy.mode == "off":
        return RoutingDecision(
            Route.BLOCKED,
            "vision is disabled",
        )

    if policy.mode == "benchmark_only":
        return RoutingDecision(
            Route.VISION_BENCHMARK_ONLY,
            "Sprint V0 benchmark-only mode never authorizes a vision click",
            locator=candidates[0],
            action_authorized=False,
        )

    if policy.mode != "fallback":
        return RoutingDecision(Route.BLOCKED, f"unsupported vision mode={policy.mode}")

    if not policy.gate_v0_passed:
        return RoutingDecision(Route.BLOCKED, "Gate V0 has not passed")

    selected: Mapping[str, Any] | None = None
    route: Route | None = None
    for item in candidates:
        kind = item.get("type")
        if kind == "vision_template" and policy.template_enabled:
            selected, route = item, Route.VISION_TEMPLATE
            break
        if (
            kind == "vision_text"
            and policy.ocr_enabled
            and policy.gate_v2_passed
        ):
            selected, route = item, Route.VISION_OCR
            break

    if selected is None or route is None:
        return RoutingDecision(
            Route.BLOCKED,
            "no eligible vision backend is enabled and gated",
        )

    high_risk = side_effect in _HIGH_RISK_SIDE_EFFECTS
    if high_risk:
        if not policy.allow_high_risk_vision:
            return RoutingDecision(
                Route.BLOCKED,
                "irreversible action vision routing is denied by default",
                locator=selected,
                require_exact_input=True,
                require_secondary_validation=True,
            )
        if not secondary_validation_available:
            return RoutingDecision(
                Route.BLOCKED,
                "irreversible action requires independent secondary validation",
                locator=selected,
                require_exact_input=True,
                require_secondary_validation=True,
            )

    return RoutingDecision(
        route,
        "explicit vision fallback eligible after semantic resolution failure",
        locator=selected,
        action_authorized=True,
        require_exact_input=high_risk,
        require_secondary_validation=high_risk,
    )
