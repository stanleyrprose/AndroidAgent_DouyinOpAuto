"""Rev3.7 static Git-managed capability Catalog: strict, no dynamic plugins.

The Catalog describes minimum policy and execution constraints. It does not
prove runtime hardware support, resolve permission, or itself allow dispatch.
A disabled/candidate definition stays discoverable but non-executable.
"""
from __future__ import annotations
import json
from pathlib import Path
import re
from typing import Any, Mapping

DEFAULT_CATALOG = Path(__file__).resolve().parents[1] / "config/capabilities.json"
_REQUIRED = {
    "android.device.observe", "android.ui.workflow",
    "android.root.exec", "tiktok.publish",
}
_NAME = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
_VERSION = re.compile(r"^[0-9]+\.[0-9]+$")


class CatalogUnavailable(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _need(ok: bool, code: str = "CAPABILITY_CATALOG_INVALID") -> None:
    if not ok:
        raise CatalogUnavailable(code)


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        _need(key not in out, "CATALOG_DUPLICATE_KEY")
        out[key] = value
    return out


def _validate(row: Mapping[str, Any]) -> dict[str, Any]:
    _need(isinstance(row, dict))
    name = row.get("name")
    _need(isinstance(name, str) and _NAME.fullmatch(name) is not None)
    _need(isinstance(row.get("version"), str)
          and _VERSION.fullmatch(row["version"]) is not None)
    _need(row.get("classification") in {"BUSINESS", "INTERNAL", "ADMIN"})
    _need(isinstance(row.get("adapter"), str) and row["adapter"])
    _need(type(row.get("enabled")) is bool)
    profile = row.get("execution_profile")
    _need(isinstance(profile, dict)
          and profile.get("placement") == "Y700_REQUIRED"
          and profile.get("alternate_runtime_fallback") == "NONE"
          and type(profile.get("requires_foreground")) is bool
          and isinstance(profile.get("readiness_requirements"), list)
          and all(isinstance(x, str) and x
                  for x in profile["readiness_requirements"]))
    policy = row.get("minimum_policy")
    _need(isinstance(policy, dict)
          and policy.get("replay") in {"NEVER", "SAFE_READ_ONLY"}
          and type(policy.get("expires_in_max_sec")) is int
          and 0 < policy["expires_in_max_sec"] <= 86400)
    if row.get("resource") == "android_ui":
        guard = row.get("overlay_policy")
        _need(isinstance(guard, dict)
              and guard.get("top_level_guard") == "REQUIRED"
              and guard.get("in_app_modal")
                  in {"NONE_KNOWN", "POSSIBLE"})
        if guard["in_app_modal"] == "POSSIBLE":
            sel = guard.get("blocking_selectors")
            _need(isinstance(sel, list) and bool(sel))
            _need(all(isinstance(x, dict)
                      and type(x.get("selector_version")) is int
                      and x.get("resource_id")
                      for x in sel))
        dispatch = row.get("dispatch_contract")
        _need(isinstance(dispatch, dict)
              and dispatch.get("version") == 1
              and isinstance(dispatch.get("allowed_routes"), list)
              and all(x in {
                  "SEMANTIC_UI", "VISION_ASSISTED_UI", "VERIFIED_NOOP",
                  "HOST_PRIMITIVE"} for x in dispatch["allowed_routes"]))
    if row["classification"] == "BUSINESS":
        _need(policy.get("approval") == "REQUIRED"
              and policy.get("verification") == "REQUIRED"
              and policy.get("replay") == "NEVER")
        app = row.get("app_ui_contract")
        _need(isinstance(app, dict) and app.get("package")
              and app.get("ui_contract_version"))
        if row["enabled"]:
            # Prevent unreviewed app-version signatures/selectors entering
            # production via a single Catalog boolean flip.
            _need(app.get("acceptance_status") == "ACCEPTED"
                  and isinstance(app.get("accepted_version_codes"), list)
                  and bool(app["accepted_version_codes"])
                  and all(type(v) is int and v > 0
                          for v in app["accepted_version_codes"])
                  and all(s.get("enabled_for_production") is True
                          for s in row["overlay_policy"]["blocking_selectors"]),
                  "APP_UI_CONTRACT_NOT_ACCEPTED")
    return dict(row)


def load_catalog(path: Path = DEFAULT_CATALOG) -> dict[str, dict[str, Any]]:
    _need(not path.is_symlink(), "CATALOG_PATH_UNTRUSTED")
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise CatalogUnavailable("CATALOG_UNAVAILABLE") from exc
    _need(0 < len(data) <= 131072, "CATALOG_SIZE_INVALID")
    try:
        doc = json.loads(data, object_pairs_hook=_unique)
    except (ValueError, UnicodeError) as exc:
        raise CatalogUnavailable("CATALOG_JSON_INVALID") from exc
    _need(isinstance(doc, dict)
          and doc.get("catalog_schema_version") == 1)
    items = doc.get("capabilities")
    _need(isinstance(items, list))
    found: dict[str, dict[str, Any]] = {}
    for raw in items:
        row = _validate(raw)
        _need(row["name"] not in found, "CATALOG_DUPLICATE_CAPABILITY")
        found[row["name"]] = row
    _need(_REQUIRED.issubset(found), "CATALOG_SHIPPING_SET_INCOMPLETE")
    return found


def public_definition(row: Mapping[str, Any]) -> dict[str, Any]:
    """No authorization, credential, adapter execution or private evidence."""
    return {
        "name": row["name"],
        "version": row["version"],
        "classification": row["classification"],
        "adapter": row["adapter"],
        "enabled": False,   # release gate is not the Catalog enabled bit
        "configured_enabled": row["enabled"],
        "placement": row["execution_profile"]["placement"],
        "requires_foreground":
            row["execution_profile"]["requires_foreground"],
        "alternate_runtime_fallback": "NONE",
        "runtime_activation_authorized": False,
    }
