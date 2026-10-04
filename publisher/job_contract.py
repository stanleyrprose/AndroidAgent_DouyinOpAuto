#!/usr/bin/env python3
import json
import re
from pathlib import Path

JOB_ID_RE=re.compile(r"^[A-Za-z0-9._-]{1,96}$")
MODES={"DRY_RUN","COMMIT"}
VISIBILITY={"PRIVATE","PUBLIC","FRIENDS"}

class ContractError(ValueError):
    pass

def load_manifest(path):
    with open(path,encoding="utf-8") as f:
        data=json.load(f)
    validate_manifest(data)
    return data

def _simple_filename(value,key):
    name=str(value)
    if Path(name).name != name or name in {"",".",".."}:
        raise ContractError(f"{key} must be a simple filename")
    return name

def validate_manifest(m):
    required=[
        "schema_version","job_id","source","target","language","status",
        "video_file","caption_file","sha256","publish_mode",
    ]
    missing=[k for k in required if k not in m]
    if missing:
        raise ContractError(f"missing fields: {missing}")
    if m["schema_version"] != 1:
        raise ContractError("schema_version must be 1")
    if not JOB_ID_RE.fullmatch(str(m["job_id"])):
        raise ContractError("invalid job_id")
    if m["target"] != "tiktok":
        raise ContractError("target must be tiktok")
    if m["status"] != "READY":
        raise ContractError("status must be READY")
    if m["publish_mode"] not in MODES:
        raise ContractError(f"publish_mode must be one of {sorted(MODES)}")

    visibility=m.get("visibility","PUBLIC")
    if visibility not in VISIBILITY:
        raise ContractError(f"visibility must be one of {sorted(VISIBILITY)}")

    filenames=[_simple_filename(m["video_file"],"video_file"),
               _simple_filename(m["caption_file"],"caption_file")]
    for key in ("title_file","metadata_file"):
        if m.get(key):
            filenames.append(_simple_filename(m[key],key))

    sha=m["sha256"]
    if not isinstance(sha,dict):
        raise ContractError("sha256 must be an object")
    for name in filenames:
        digest=sha.get(name)
        if not isinstance(digest,str) or not re.fullmatch(r"[0-9a-fA-F]{64}",digest):
            raise ContractError(f"missing/invalid sha256 for {name}")
    return True

def write_json_atomic(path,data):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    with open(tmp,"w",encoding="utf-8") as f:
        json.dump(data,f,ensure_ascii=False,indent=2)
        f.write("\n")
        f.flush()
    tmp.replace(path)
