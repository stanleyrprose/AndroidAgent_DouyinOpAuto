"""Rev3.7 versioned, conservative top-level overlay classification.

Pure policy function for an independently observed Android window inventory.
Not a screenshot classifier or a production mutation authorization.

No assumption that every second window blocks; IME and passive notifications
are handled distinctly. An empty/incomplete/untrusted inventory cannot prove
CLEAR. App-internal modals require a separately watched semantic selector.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence


class OverlayStatus(str, Enum):
    CLEAR_READ_ONLY = "READ_ONLY_NO_BLOCKER_FOUND"
    BLOCKED = "UNEXPECTED_BLOCKING_OVERLAY"
    UNAVAILABLE = "OVERLAY_CLASSIFICATION_UNAVAILABLE"


@dataclass(frozen=True)
class OverlayVerdict:
    status: OverlayStatus
    owner_package: str | None = None
    window_class: str | None = None
    reason: str = ""

    def safe_receipt(self) -> dict[str, Any]:
        """Diagnostic only; does not mint blocking_overlay_present=false."""
        return {
            "status": self.status.value,
            "reason": self.reason,
            "blocking_overlay_classification_available":
                self.status != OverlayStatus.UNAVAILABLE,
            "production_dispatch_authorized": False,
            "dg3_status": "OPEN",
            "action_attempts": 0,
        }


@dataclass(frozen=True)
class WindowContract:
    id: str
    foreground_package: str
    action_kind: str
    allow_input_method: bool


# Static, versioned internal contracts: caller cannot add an allowlist entry.
_CONTRACTS = {
    "tiktok.create.observe.v1": WindowContract(
        "tiktok.create.observe.v1", "com.zhiliaoapp.musically", "TAP", False
    ),
    "android.settings.observe.v1": WindowContract(
        "android.settings.observe.v1", "com.android.settings", "TAP", False
    ),
    "android.settings.text-entry.v1": WindowContract(
        "android.settings.text-entry.v1", "com.android.settings", "TEXT", True
    ),
}
_WINDOW_TYPES = frozenset({
    "APPLICATION", "INPUT_METHOD", "SYSTEM",
    "ACCESSIBILITY_OVERLAY", "OTHER",
})


def _unknown(code: str) -> OverlayVerdict:
    return OverlayVerdict(OverlayStatus.UNAVAILABLE, reason=code)


def _blocked(record: Mapping[str, Any], code: str) -> OverlayVerdict:
    return OverlayVerdict(
        OverlayStatus.BLOCKED,
        owner_package=str(record.get("owner_package", ""))[:120] or None,
        window_class=str(record.get("window_class", ""))[:120] or None,
        reason=code,
    )


def _bounds(value: Any) -> tuple[int, int, int, int] | None:
    if not isinstance(value, (tuple, list)) or len(value) != 4:
        return None
    if not all(type(item) is int for item in value):
        return None
    l, t, r, b = value
    return (l, t, r, b) if 0 <= l < r and 0 <= t < b else None


def _intersects(a: tuple[int, int, int, int],
                b: tuple[int, int, int, int]) -> bool:
    return min(a[2], b[2]) > max(a[0], b[0]) and (
        min(a[3], b[3]) > max(a[1], b[1])
    )


def classify_window_facts_readonly(
    *,
    contract_id: str,
    foreground_package: str,
    inventory: Mapping[str, Any],
    target_bounds: Sequence[int],
    semantic_modal_guard_clear: bool | None,
) -> OverlayVerdict:
    """Interpret a snapshot obtained independently by the platform observer.

    No caller-facing workflow value can override a frozen contract. The
    observation adapter must prove completeness and accurate focus/visibility;
    until then this function returns UNAVAILABLE rather than inventing CLEAR.
    A CLEAR_READ_ONLY result is not a production JIT action authorization.
    """
    contract = _CONTRACTS.get(contract_id)
    if contract is None or contract.foreground_package != foreground_package:
        return _unknown("OVERLAY_CONTRACT_UNAVAILABLE")
    target = _bounds(target_bounds)
    if target is None:
        return _unknown("OVERLAY_TARGET_GEOMETRY_UNAVAILABLE")
    if semantic_modal_guard_clear is not True:
        return _unknown("SEMANTIC_MODAL_GUARD_UNAVAILABLE")
    if not isinstance(inventory, Mapping):
        return _unknown("WINDOW_INVENTORY_UNAVAILABLE")
    if inventory.get("inventory_version") != 1:
        return _unknown("WINDOW_INVENTORY_VERSION_MISMATCH")
    if (inventory.get("complete") is not True
            or inventory.get("observer_trusted") is not True
            or inventory.get("foreground_package") != foreground_package):
        return _unknown("WINDOW_INVENTORY_NOT_AUTHORITATIVE")

    windows = inventory.get("windows")
    if not isinstance(windows, list) or not windows or len(windows) > 80:
        return _unknown("WINDOW_INVENTORY_EMPTY_OR_EXCESSIVE")

    app_candidates = 0
    app_active = False
    ime_focused = False
    focus_count = 0
    unknown_nonblocker = False

    for row in windows:
        if not isinstance(row, Mapping):
            return _unknown("WINDOW_FACTS_MALFORMED")
        kind = row.get("type")
        if kind not in _WINDOW_TYPES:
            return _unknown("WINDOW_TYPE_UNCLASSIFIED")
        owner = row.get("owner_package")
        if not isinstance(owner, str) or not owner:
            return _unknown("WINDOW_OWNER_MISSING")
        if not isinstance(row.get("window_class"), str) or not row["window_class"]:
            return _unknown("WINDOW_CLASS_MISSING")
        for key in ("visible", "focused", "active", "touchable"):
            if type(row.get(key)) is not bool:
                return _unknown("WINDOW_FOCUS_OR_INPUT_UNKNOWN")
        bounds = _bounds(row.get("bounds"))
        if bounds is None:
            return _unknown("WINDOW_GEOMETRY_UNKNOWN")
        visible, focused, active = (
            row["visible"], row["focused"], row["active"]
        )
        intercepts = row["touchable"] and _intersects(bounds, target)
        if focused:
            focus_count += 1
        if not visible:
            if focused or active:
                return _unknown("HIDDEN_ACTIVE_WINDOW")
            continue

        if kind == "APPLICATION" and owner == foreground_package:
            app_candidates += 1
            if active:
                app_active = True
            if intercepts or focused:
                # Additional same-app dialogs must be explicitly recognized
                # by the semantic modal guard and action profile.
                if row.get("is_primary_root") is not True:
                    return _blocked(row, "UNEXPECTED_SAME_APP_WINDOW")
            continue

        if kind == "INPUT_METHOD":
            if focused:
                ime_focused = True
            # IME mere presence does not constitute a blocker per PRD.
            if contract.allow_input_method:
                if active or focused:
                    continue
                # Nonfocused IME is harmless if non-intercepting.
                if not intercepts:
                    continue
                return _unknown("IME_TARGET_INTERSECTION_UNVERIFIED")
            if focused or active or intercepts:
                return _blocked(row, "UNEXPECTED_INPUT_METHOD")
            continue

        if kind == "ACCESSIBILITY_OVERLAY":
            # No audited non-intercepting overlay allowlist yet. Presence
            # alone is not positive BLOCKING proof, but is not clear either.
            if focused or active or intercepts:
                return _blocked(row, "UNKNOWN_ACCESSIBILITY_OVERLAY_INPUT")
            unknown_nonblocker = True
            continue

        if kind == "SYSTEM":
            # Passive/toast-like windows are not blockers on presence alone.
            if focused or active or intercepts:
                return _blocked(row, "FOCUSED_OR_INTERCEPTING_SYSTEM_WINDOW")
            continue

        if kind in ("APPLICATION", "OTHER"):
            if focused or active or intercepts:
                return _blocked(row, "UNEXPECTED_FOCUS_OR_TARGET_INTERCEPTION")
            # Foreign passive windows do not prove target unsafe, but until
            # versioned policy classifies them they prevent a clear verdict.
            unknown_nonblocker = True

    if app_candidates != 1 or not app_active:
        return _unknown("EXPECTED_APP_ROOT_UNAVAILABLE")
    if focus_count != 1:
        return _unknown("FOCUS_CARDINALITY_UNVERIFIED")
    if unknown_nonblocker:
        return _unknown("UNKNOWN_VISIBLE_WINDOW")
    if contract.allow_input_method:
        # Either app has focus or text-input IME has sole focus. This
        # still requires a separate targeted semantic focus guard.
        if not ime_focused and not any(
            row.get("focused") is True and
            row.get("owner_package") == foreground_package
            for row in windows
        ):
            return _unknown("TEXT_FOCUS_UNVERIFIED")
    else:
        if not any(
            row.get("focused") is True and
            row.get("owner_package") == foreground_package
            for row in windows
        ):
            return _unknown("FOREGROUND_FOCUS_UNVERIFIED")
    return OverlayVerdict(OverlayStatus.CLEAR_READ_ONLY, reason="CLASSIFIED_READ_ONLY")
