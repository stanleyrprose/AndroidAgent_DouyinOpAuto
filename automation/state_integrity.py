#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
import unicodedata
from pathlib import Path
from typing import Any

RUNTIME = Path(os.environ.get("Y700_RUNTIME", "/opt/y700/runtime"))
STATE_DIR = Path(os.environ.get("Y700_UI_STATE_DIR", str(RUNTIME / "ui-state")))
STATE_PATH = STATE_DIR / "device-state.json"
FINGERPRINT_VERSION = "semantic-v1"
MAX_TOKEN_AGE_MS = 30_000

PROFILES: dict[str, dict[str, Any]] = {
    "semantic-v1.foreground-base.v1": {
        "scope": "FOREGROUND",
        "watch_element_optional": [],
        "watch_properties": [],
    },
    "generic.element-base.v1": {
        "scope": "ELEMENT",
        "watch_element_optional": [],
        "watch_properties": [],
    },
    "generic.ordinal-element.v1": {
        "scope": "ELEMENT",
        "watch_element_optional": [],
        "watch_properties": ["target_ordinal"],
    },
    "settings.switch.element-base.v1": {
        "scope": "ELEMENT",
        "watch_element_optional": [],
        "watch_properties": [],
    },
    "tiktok.publish-control.v1": {
        "scope": "ELEMENT",
        "watch_element_optional": ["text", "content_desc"],
        "watch_properties": [],
    },
}


class StateIntegrityError(RuntimeError):
    pass


def _now_iso() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat()


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _ensure_dir() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(STATE_DIR, 0o700)


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    _ensure_dir()
    tmp = path.with_name(path.name + ".tmp-" + secrets.token_hex(4))
    raw = (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    with open(tmp, "wb") as f:
        os.fchmod(f.fileno(), 0o600)
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    os.chmod(path, 0o600)
    _fsync_dir(path.parent)


def _boot_id() -> str:
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise StateIntegrityError("STATE_INTEGRITY_UNAVAILABLE: boot_id") from exc


def _boottime_ms() -> int:
    try:
        return int(time.clock_gettime(time.CLOCK_BOOTTIME) * 1000)
    except (AttributeError, OSError) as exc:
        raise StateIntegrityError("STATE_INTEGRITY_UNAVAILABLE: CLOCK_BOOTTIME") from exc


def load_state() -> dict[str, Any]:
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        state = {
            "state_version": 1,
            "state_epoch": "epoch-" + secrets.token_hex(16),
            "revision": 0,
            "fingerprint_version": FINGERPRINT_VERSION,
            "initialized_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        _atomic_json(STATE_PATH, state)
        return state
    except (OSError, json.JSONDecodeError) as exc:
        raise StateIntegrityError("STATE_INTEGRITY_UNAVAILABLE: device-state corrupt") from exc
    if (
        not isinstance(state, dict)
        or state.get("state_version") != 1
        or not isinstance(state.get("state_epoch"), str)
        or not isinstance(state.get("revision"), int)
        or state.get("revision", -1) < 0
    ):
        raise StateIntegrityError("STATE_INTEGRITY_UNAVAILABLE: invalid device-state")
    return state


def _normalize(value: Any) -> Any:
    if value is None or isinstance(value, bool) or isinstance(value, int):
        return value
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, float):
        raise ValueError("floats forbidden in semantic-v1")
    if isinstance(value, list):
        raise ValueError("arrays forbidden in semantic-v1")
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = unicodedata.normalize("NFC", str(key))
            if normalized_key in out:
                raise ValueError("duplicate key after NFC normalization")
            out[normalized_key] = _normalize(item)
        return out
    raise ValueError(f"unsupported semantic type: {type(value).__name__}")


def canonical_bytes(snapshot: dict[str, Any]) -> bytes:
    normalized = _normalize(snapshot)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def semantic_hash(snapshot: dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(snapshot)).hexdigest()


def _selector_value(selector: dict[str, Any], key: str) -> Any:
    if key == "class_name":
        return selector.get("class_name")
    return selector.get(key)


def _element_value(element: dict[str, Any], key: str) -> Any:
    if key == "class_name":
        return element.get("class")
    return element.get(key)


def _match_simple(element: dict[str, Any], selector: dict[str, Any]) -> bool:
    key_map = {
        "resource_id": "resource_id",
        "class_name": "class",
        "package": "package",
        "text": "text",
        "content_desc": "content_desc",
        "clickable": "clickable",
        "enabled": "enabled",
        "selected": "selected",
        "checked": "checked",
        "checkable": "checkable",
        "scrollable": "scrollable",
    }
    for sk, ek in key_map.items():
        if sk in selector and element.get(ek) != selector.get(sk):
            return False
    if "text_contains" in selector and str(selector["text_contains"]) not in str(element.get("text") or ""):
        return False
    if "content_desc_contains" in selector and str(selector["content_desc_contains"]) not in str(element.get("content_desc") or ""):
        return False
    return True


def match_elements(observation: dict[str, Any], selector: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [row for row in (observation.get("elements") or []) if isinstance(row, dict)]
    by_id = {row.get("node_id"): row for row in rows if row.get("node_id")}
    children: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        parent_id = row.get("parent_id")
        if parent_id:
            children.setdefault(parent_id, []).append(row)

    def parent(row: dict[str, Any]) -> dict[str, Any] | None:
        pid = row.get("parent_id")
        return by_id.get(pid) if pid else None

    out: list[dict[str, Any]] = []
    for row in rows:
        if not _match_simple(row, selector):
            continue
        ps = selector.get("has_parent")
        if isinstance(ps, dict):
            p = parent(row)
            if p is None or not _match_simple(p, ps):
                continue
        anc = selector.get("has_ancestor")
        if isinstance(anc, dict):
            p = parent(row)
            found = False
            while p is not None:
                if _match_simple(p, anc):
                    found = True
                    break
                p = parent(p)
            if not found:
                continue
        desc = selector.get("has_descendant")
        if isinstance(desc, dict):
            stack = list(children.get(row.get("node_id"), []))
            found = False
            while stack:
                child = stack.pop()
                if _match_simple(child, desc):
                    found = True
                    break
                stack.extend(children.get(child.get("node_id"), []))
            if not found:
                continue
        out.append(row)
    return out


def profile_for_action(action: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    explicit = action.get("fingerprint_profile_id")
    if explicit is not None:
        if explicit not in PROFILES:
            raise StateIntegrityError("STATE_TOKEN_PROFILE_MISMATCH")
        return str(explicit), PROFILES[str(explicit)]
    name = str(action.get("action", ""))
    if name in {"pressBack", "pressHome", "swipe", "scroll", "appForceStop", "appLaunch"}:
        pid = "semantic-v1.foreground-base.v1"
    elif name == "tapObserved":
        pid = "generic.ordinal-element.v1"
    elif action.get("side_effect") == "EXTERNAL_IRREVERSIBLE":
        pid = "tiktok.publish-control.v1"
    else:
        pid = "generic.element-base.v1"
    return pid, PROFILES[pid]


def _selector_projection(selector: dict[str, Any]) -> dict[str, Any]:
    allowed = (
        "resource_id", "class_name", "package", "text", "content_desc",
        "text_contains", "content_desc_contains",
        "clickable", "enabled", "checked", "selected",
    )
    out = {k: selector[k] for k in allowed if k in selector}
    for relation in ("has_parent", "has_ancestor", "has_descendant"):
        nested = selector.get(relation)
        if isinstance(nested, dict):
            out[relation] = _selector_projection(nested)
    return out


def project_snapshot(
    observation: dict[str, Any],
    *,
    interactive: bool,
    keyguard_locked: bool,
    activity: str,
    blocking_overlay_present: bool,
    blocking_overlay_owner_package: str | None,
    blocking_overlay_class: str | None,
    action: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    profile_id, profile = profile_for_action(action)
    package = observation.get("package")
    if not isinstance(package, str) or not package or not isinstance(activity, str) or not activity:
        raise StateIntegrityError("STATE_FINGERPRINT_UNAVAILABLE")
    if blocking_overlay_present:
        raise StateIntegrityError("UNEXPECTED_BLOCKING_OVERLAY")

    snapshot: dict[str, Any] = {
        "fingerprint_version": FINGERPRINT_VERSION,
        "scope": profile["scope"],
        "screen": {
            "interactive": bool(interactive),
            "keyguard_locked": bool(keyguard_locked),
            "blocking_overlay_present": bool(blocking_overlay_present),
            "blocking_overlay_owner_package": blocking_overlay_owner_package,
            "blocking_overlay_class": blocking_overlay_class,
        },
        "foreground": {
            "package": package,
            "activity": activity,
        },
    }
    if profile["scope"] == "FOREGROUND":
        return snapshot, profile_id

    selector = action.get("selector")
    if not isinstance(selector, dict) or not selector:
        raise StateIntegrityError("STATE_FINGERPRINT_UNAVAILABLE")
    matches = match_elements(observation, selector)
    if action.get("action") == "tapObserved":
        matches = sorted(
            matches,
            key=lambda row: (
                (row.get("bounds") or [0, 0, 0, 0])[1],
                (row.get("bounds") or [0, 0, 0, 0])[0],
            ),
        )
    ordinal = int(action.get("ordinal", 0)) if action.get("action") == "tapObserved" else 0
    if ordinal < 0 or ordinal >= len(matches):
        raise StateIntegrityError("STATE_FINGERPRINT_UNAVAILABLE")
    if action.get("action") != "tapObserved" and len(matches) != 1:
        raise StateIntegrityError("STATE_FINGERPRINT_UNAVAILABLE")
    target = matches[ordinal]

    snapshot["selector"] = _selector_projection(selector)
    snapshot["cardinality"] = len(matches)
    elem = {
        "enabled": bool(target.get("enabled", False)),
        "checked": bool(target.get("checked", False)),
        "selected": bool(target.get("selected", False)),
        "clickable": bool(target.get("clickable", False)),
    }
    optional = set(profile.get("watch_element_optional") or [])
    if "text" in optional:
        elem["text"] = target.get("text")
    if "content_desc" in optional:
        elem["content_desc"] = target.get("content_desc")
    snapshot["element"] = elem

    props: dict[str, Any] = {}
    if "target_ordinal" in set(profile.get("watch_properties") or []):
        props["target_ordinal"] = ordinal
    if props:
        snapshot["property"] = props
    return snapshot, profile_id


def issue_token(
    snapshot: dict[str, Any],
    *,
    fingerprint_profile_id: str,
    max_age_ms: int = MAX_TOKEN_AGE_MS,
    boot_id: str | None = None,
    boottime_ms: int | None = None,
) -> dict[str, Any]:
    if fingerprint_profile_id not in PROFILES:
        raise StateIntegrityError("STATE_TOKEN_PROFILE_MISMATCH")
    if not 0 < int(max_age_ms) <= MAX_TOKEN_AGE_MS:
        raise StateIntegrityError("STATE_TOKEN_MAX_AGE_INVALID")
    state = load_state()
    return {
        "token_version": 1,
        "state_epoch": state["state_epoch"],
        "revision": state["revision"],
        "fingerprint_version": FINGERPRINT_VERSION,
        "fingerprint_profile_id": fingerprint_profile_id,
        "scope": PROFILES[fingerprint_profile_id]["scope"],
        "state_hash": semantic_hash(snapshot),
        "observed_at": _now_iso(),
        "observed_boot_id": boot_id or _boot_id(),
        "observed_boottime_ms": int(boottime_ms if boottime_ms is not None else _boottime_ms()),
        "max_age_ms": int(max_age_ms),
    }


def assert_token(
    token: Any,
    snapshot: dict[str, Any],
    *,
    expected_profile_id: str,
    boot_id: str | None = None,
    boottime_ms: int | None = None,
) -> dict[str, Any]:
    if not isinstance(token, dict) or token.get("token_version") != 1:
        raise StateIntegrityError("UNGUARDED_MUTATION_NOT_ALLOWED")
    state = load_state()
    if token.get("state_epoch") != state.get("state_epoch"):
        raise StateIntegrityError("STALE_STATE_EPOCH")
    if token.get("revision") != state.get("revision"):
        raise StateIntegrityError("STALE_STATE_REVISION")
    if token.get("fingerprint_version") != FINGERPRINT_VERSION:
        raise StateIntegrityError("STALE_STATE_HASH")
    if token.get("fingerprint_profile_id") != expected_profile_id:
        raise StateIntegrityError("STATE_TOKEN_PROFILE_MISMATCH")
    current_boot = boot_id or _boot_id()
    if token.get("observed_boot_id") != current_boot:
        raise StateIntegrityError("STATE_TOKEN_BOOT_MISMATCH")
    now_ms = int(boottime_ms if boottime_ms is not None else _boottime_ms())
    observed = token.get("observed_boottime_ms")
    max_age = token.get("max_age_ms")
    if not isinstance(observed, int) or not isinstance(max_age, int) or max_age <= 0 or max_age > MAX_TOKEN_AGE_MS:
        raise StateIntegrityError("STATE_TOKEN_EXPIRED")
    age = now_ms - observed
    if age < 0:
        raise StateIntegrityError("STATE_TOKEN_BOOT_MISMATCH")
    if age > max_age:
        raise StateIntegrityError("STATE_TOKEN_EXPIRED")
    if token.get("state_hash") != semantic_hash(snapshot):
        raise StateIntegrityError("STALE_STATE_HASH")
    return token


def advance_revision() -> tuple[int, int]:
    state = load_state()
    before = int(state["revision"])
    after = before + 1
    updated = dict(state)
    updated["revision"] = after
    updated["updated_at"] = _now_iso()
    _atomic_json(STATE_PATH, updated)
    return before, after


def bump_epoch(reason: str) -> dict[str, Any]:
    state = load_state()
    updated = dict(state)
    updated["state_epoch"] = "epoch-" + secrets.token_hex(16)
    updated["revision"] = 0
    updated["updated_at"] = _now_iso()
    updated["invalidation_reason"] = str(reason)[:256]
    _atomic_json(STATE_PATH, updated)
    return updated
