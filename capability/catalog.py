from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DEFAULT_CATALOG=ROOT/"config"/"capabilities.json"
class CatalogError(RuntimeError): pass
def load_catalog(path:Path=DEFAULT_CATALOG):
    raw=json.loads(path.read_text(encoding="utf-8"))
    rows=raw.get("capabilities")
    if raw.get("schema_version")!=1 or not isinstance(rows,list): raise CatalogError("CAPABILITY_CATALOG_INVALID")
    out={}
    for row in rows:
        name=row.get("name"); version=row.get("version")
        if not name or not version or name in out: raise CatalogError("CAPABILITY_CATALOG_INVALID")
        if row.get("classification") not in {"BUSINESS","INTERNAL","ADMIN"}: raise CatalogError("CAPABILITY_CATALOG_INVALID")
        if row.get("resource")=="android_ui":
            overlay=row.get("overlay_policy") or {}
            if overlay.get("top_level_guard")!="REQUIRED": raise CatalogError("CAPABILITY_CATALOG_INVALID")
            if overlay.get("in_app_modal") not in {"NONE_KNOWN","POSSIBLE"}: raise CatalogError("CAPABILITY_CATALOG_INVALID")
            if overlay.get("in_app_modal")=="POSSIBLE" and not overlay.get("blocking_selectors"): raise CatalogError("CAPABILITY_CATALOG_INVALID")
        policy=row.get("minimum_policy") or {}
        if policy.get("replay") not in {"SAFE","IDEMPOTENT","NEVER"}: raise CatalogError("CAPABILITY_CATALOG_INVALID")
        out[name]=row
    return out
def resolve(name,version,path:Path=DEFAULT_CATALOG):
    row=load_catalog(path).get(name)
    if not row: raise CatalogError("CAPABILITY_NOT_FOUND")
    if row["version"]!=version: raise CatalogError("CAPABILITY_VERSION_MISMATCH")
    return row
