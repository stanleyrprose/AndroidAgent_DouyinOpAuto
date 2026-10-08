#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

ROUTE_CLASSES = {"VERIFIED_NOOP","SEMANTIC_UI","VISION_ASSISTED_UI","HOST_PRIMITIVE","BLOCKED"}

def capability_axes(*, runtime_support: bool|None, advertised: bool, permission: str, readiness: str) -> dict[str, Any]:
    if runtime_support is True and not advertised:
        support="SUPPORTED_UNADVERTISED"; reasons=["CAPABILITY_CATALOG_DRIFT"]
    elif runtime_support is True:
        support="SUPPORTED"; reasons=[]
    elif runtime_support is False:
        support="UNSUPPORTED"; reasons=[]
    else:
        support="UNKNOWN"; reasons=[]
    return {"support_state":support,"permission_state":permission,"readiness_state":readiness,"reason_codes":reasons}

def select_route(*, target_satisfied: bool, semantic_available: bool, visual_allowed: bool, frame_fresh: bool, host_primitive_allowed: bool, external_irreversible: bool=False, visual_fallback_approved: bool=False) -> str:
    if target_satisfied: return "VERIFIED_NOOP"
    if semantic_available: return "SEMANTIC_UI"
    if visual_allowed and frame_fresh and (not external_irreversible or visual_fallback_approved): return "VISION_ASSISTED_UI"
    if host_primitive_allowed: return "HOST_PRIMITIVE"
    return "BLOCKED"

def validate_frame(frame: dict[str,Any], locator: dict[str,Any], current: dict[str,Any], now_boottime_ms: int) -> tuple[bool,str]:
    if locator.get("frame_id") != frame.get("frame_id"): return False,"LOCATOR_FRAME_MISMATCH"
    if frame.get("observed_boot_id") != current.get("observed_boot_id"): return False,"FRAME_BOOT_MISMATCH"
    if frame.get("state_epoch") != current.get("state_epoch"): return False,"FRAME_STATE_EPOCH_STALE"
    if frame.get("revision") != current.get("revision"): return False,"FRAME_REVISION_STALE"
    if frame.get("display_id") != current.get("display_id"): return False,"FRAME_DISPLAY_CHANGED"
    if frame.get("rotation") != current.get("rotation"): return False,"FRAME_ROTATION_CHANGED"
    if (frame.get("width"),frame.get("height")) != (current.get("width"),current.get("height")): return False,"FRAME_DISPLAY_CHANGED"
    if frame.get("foreground") != current.get("foreground"): return False,"FRAME_FOREGROUND_DRIFT"
    age=now_boottime_ms-int(frame.get("captured_boottime_ms",0))
    if age < 0 or age > int(frame.get("max_age_ms",0)): return False,"FRAME_STALE"
    return True,"PASS"

def rollback_decision(*, patch_class: str, quiescent: bool, postcheck_pass: bool, candidate_mutation_seen: bool, ambiguity: bool) -> str:
    if patch_class!="PATCH_SAFE": return "MANUAL_ONLY"
    if not quiescent: return "UPGRADE_REQUIRES_QUIESCENCE"
    if postcheck_pass: return "ACTIVATE"
    if candidate_mutation_seen or ambiguity: return "ROLLBACK_NOT_SAFE"
    return "ROLLBACK_TO_LAST_KNOWN_GOOD"

STAGES=["control_plane","device_connectivity","observation_source","frame_acquisition","frame_freshness","target_localization","permission","resource_ownership","state_guard","action_dispatch","postcondition","business_verification"]
def stage_failure(stage: str, reason: str) -> dict[str,Any]:
    if stage not in STAGES: raise ValueError(stage)
    idx=STAGES.index(stage)
    return {"failure_stage":stage,"reason_code":reason,"last_success_stage":STAGES[idx-1] if idx else None}
