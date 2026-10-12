"""Rev3.7 capability support / permission / readiness read-only model.

The three axes are independently derived; this module never invokes a
backend, acquires a resource, writes approval/effect state, or opens BUSINESS
mutation. A physical adapter may be present while approval is missing, and a
Catalog omission is a diagnosable drift rather than proof of non-support.

This is an offline Gateway-domain implementation building block only.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class Support(str, Enum):
    SUPPORTED = "SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    UNKNOWN = "UNKNOWN"
    SUPPORTED_UNADVERTISED = "SUPPORTED_UNADVERTISED"


class Permission(str, Enum):
    ALLOWED = "ALLOWED"
    DENIED = "DENIED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    POLICY_UNRESOLVED = "POLICY_UNRESOLVED"


class Readiness(str, Enum):
    UNKNOWN = "UNKNOWN"
    READY = "READY"
    DEGRADED = "DEGRADED"
    BUSY = "BUSY"
    BLOCKED_RECONCILE = "BLOCKED_RECONCILE"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class CapabilityDefinition:
    name: str
    version: str
    effect_class: str
    runtime: str
    advertised: bool
    # A minimum gate, not a request-supplied permission override.
    requires_approval: bool


# Static catalogue candidates only; not an executable registry. All BUSINESS
# invocations are disabled independently until full release acceptance.
_DEFINITIONS: dict[str, CapabilityDefinition] = {
    "android.device.observe": CapabilityDefinition(
        "android.device.observe", "1.0", "OBSERVE_ONLY", "Y700", True, False
    ),
    "android.ui.workflow": CapabilityDefinition(
        "android.ui.workflow", "1.0", "LOCAL_UI_MUTATION", "Y700", True, True
    ),
    "android.root.exec": CapabilityDefinition(
        "android.root.exec", "1.0", "ROOT_UNKNOWN_MUTATION",
        "Y700", True, True
    ),
    "tiktok.publish": CapabilityDefinition(
        "tiktok.publish", "1.0", "EXTERNAL_IRREVERSIBLE", "Y700", False, True
    ),
}


@dataclass(frozen=True)
class Axis:
    state: str
    reason_codes: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {"state": self.state, "reason_codes": list(self.reason_codes),
                "evidence": list(self.evidence)}


@dataclass(frozen=True)
class CapabilityView:
    name: str
    version: str | None
    support: Axis
    permission: Axis
    readiness: Axis
    diagnostics: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "capability": self.name,
            "version": self.version,
            "support": self.support.as_dict(),
            "permission": self.permission.as_dict(),
            "readiness": self.readiness.as_dict(),
            "diagnostics": list(self.diagnostics),
            "execution_authorized": False,
            "business_activation_enabled": False,
        }


def _strict_bool(value: Any) -> bool | None:
    return value if type(value) is bool else None


def inspect_capability_readonly(
    name: str,
    *,
    runtime_facts: Mapping[str, Any],
    trusted_policy_facts: Mapping[str, Any],
    catalog_advertised: bool | None = None,
) -> CapabilityView:
    """Advisory diagnostic, NOT a permission token.

    runtime_facts are measured by the registered host/device adapter;
    trusted_policy_facts are supplied by a future authenticated policy
    component, *never* extracted from requested_by metadata or workflow JSON.
    Unknown/missing facts remain UNKNOWN rather than borrowing another axis.
    """
    definition = _DEFINITIONS.get(name)
    advertised = (
        catalog_advertised if type(catalog_advertised) is bool
        else definition.advertised if definition else False
    )
    adapter = _strict_bool(runtime_facts.get("adapter_present"))
    contract_compatible = _strict_bool(runtime_facts.get("app_ui_contract_match"))
    runtime_compatible = _strict_bool(runtime_facts.get("runtime_compatible"))
    diag: list[str] = []

    if adapter is True and contract_compatible is True and runtime_compatible is True:
        if advertised:
            support = Axis(
                Support.SUPPORTED.value, evidence=(
                    "adapter_present", "app_ui_contract_match",
                    "runtime_compatible",
                ),
            )
        else:
            support = Axis(
                Support.SUPPORTED_UNADVERTISED.value,
                reason_codes=("CAPABILITY_CATALOG_DRIFT",),
                evidence=("adapter_present", "app_ui_contract_match"),
            )
            diag.append("CAPABILITY_CATALOG_DRIFT")
    elif adapter is False or contract_compatible is False or runtime_compatible is False:
        support = Axis(
            Support.UNSUPPORTED.value,
            reason_codes=("RUNTIME_OR_ADAPTER_UNSUPPORTED",),
        )
    else:
        support = Axis(
            Support.UNKNOWN.value,
            reason_codes=("SUPPORT_EVIDENCE_INCOMPLETE",),
        )

    authenticated = _strict_bool(trusted_policy_facts.get("identity_authenticated"))
    allowed = _strict_bool(trusted_policy_facts.get("effective_policy_allows"))
    approved = _strict_bool(trusted_policy_facts.get("current_approval_valid"))
    if authenticated is False or allowed is False:
        permission = Axis(
            Permission.DENIED.value,
            reason_codes=("PERMISSION_DENIED",),
        )
    elif authenticated is not True or allowed is None:
        permission = Axis(
            Permission.POLICY_UNRESOLVED.value,
            reason_codes=("POLICY_IDENTITY_OR_RULES_UNAVAILABLE",),
        )
    elif definition is None:
        permission = Axis(
            Permission.POLICY_UNRESOLVED.value,
            reason_codes=("CAPABILITY_CONTRACT_UNAVAILABLE",),
        )
    elif definition.requires_approval and approved is not True:
        permission = Axis(
            Permission.APPROVAL_REQUIRED.value,
            reason_codes=("BUSINESS_EXTERNAL_EFFECT",),
        )
    else:
        permission = Axis(
            Permission.ALLOWED.value,
            evidence=("authenticated_identity", "effective_minimum_policy"),
        )

    # Exclusive resource and uncertain effects take precedence over readiness
    # claims. An absent signal is UNKNOWN, never READY.
    reconcile = _strict_bool(runtime_facts.get("reconcile_required"))
    resource_busy = _strict_bool(runtime_facts.get("resource_busy"))
    dependencies_ready = _strict_bool(runtime_facts.get("dependencies_ready"))
    runtime_available = _strict_bool(runtime_facts.get("runtime_available"))
    degraded = _strict_bool(runtime_facts.get("runtime_degraded"))

    if reconcile is True:
        readiness = Axis(
            Readiness.BLOCKED_RECONCILE.value,
            reason_codes=("UNRESOLVED_EFFECT_OR_BACKEND",),
        )
    elif resource_busy is True:
        readiness = Axis(Readiness.BUSY.value, reason_codes=("DEVICE_BUSY",))
    elif runtime_available is False:
        readiness = Axis(
            Readiness.UNAVAILABLE.value, reason_codes=("RUNTIME_UNAVAILABLE",),
        )
    elif degraded is True:
        readiness = Axis(
            Readiness.DEGRADED.value, reason_codes=("RUNTIME_DEGRADED",),
        )
    elif all(x is not None for x in (
        reconcile, resource_busy, dependencies_ready, runtime_available, degraded
    )) and dependencies_ready is True and runtime_available is True:
        readiness = Axis(
            Readiness.READY.value, evidence=("dependencies_ready",),
        )
    else:
        readiness = Axis(
            Readiness.UNKNOWN.value,
            reason_codes=("READINESS_EVIDENCE_INCOMPLETE",),
        )

    return CapabilityView(
        name=name,
        version=definition.version if definition else None,
        support=support,
        permission=permission,
        readiness=readiness,
        diagnostics=tuple(diag),
    )


def readonly_admission_explanation(view: CapabilityView) -> dict[str, Any]:
    """Outcome code only: a positive 3-axis view never authorizes execution."""
    if view.permission.state == Permission.DENIED.value:
        code = "PERMISSION_DENIED"
    elif view.permission.state == Permission.APPROVAL_REQUIRED.value:
        code = "APPROVAL_REQUIRED"
    elif view.permission.state == Permission.POLICY_UNRESOLVED.value:
        code = "POLICY_UNRESOLVED"
    elif "CAPABILITY_CATALOG_DRIFT" in view.diagnostics:
        code = "CAPABILITY_CATALOG_DRIFT"
    elif view.support.state != Support.SUPPORTED.value:
        code = "CAPABILITY_UNAVAILABLE"
    elif view.readiness.state != Readiness.READY.value:
        code = "CAPABILITY_NOT_READY"
    else:
        code = "GATEWAY_NOT_ACTIVATED"
    return {
        "status": "BLOCKED",
        "reason_code": code,
        "execution_authorized": False,
        "backend_submitted": False,
        "action_attempts": 0,
    }
