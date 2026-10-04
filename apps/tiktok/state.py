#!/usr/bin/env python3
"""TikTok semantic state detection over the generic Android Automation Core tree."""
from __future__ import annotations

from typing import Any

TIKTOK = "com.zhiliaoapp.musically"


def detect_state(elements: list[dict[str, Any]]) -> dict[str, Any]:
    ids = {str(x.get("resource_id") or "").strip() for x in elements if x.get("resource_id")}
    texts = {str(x.get("text") or "").strip() for x in elements if x.get("text")}
    descs = {str(x.get("content_desc") or "").strip() for x in elements if x.get("content_desc")}
    packages = {str(x.get("package") or "").strip() for x in elements if x.get("package")}

    state = "UNKNOWN"
    evidence: list[str] = []

    if "com.android.systemui" in packages and (
        "com.android.systemui:id/keyguard_root_view" in ids
        or "com.android.systemui:id/device_entry_icon_fg" in ids
    ):
        state = "KEYGUARD"
        evidence.append("systemui_keyguard")
    elif "通过短信获取更新信息？" in texts and f"{TIKTOK}:id/e62" in ids:
        state = "SMS_PROMPT"
        evidence.append("sms_updates_prompt")
    elif "谁可以看" in texts and "仅自己" in texts:
        state = "VISIBILITY"
        evidence.append("visibility_sheet")
    elif f"{TIKTOK}:id/st6" in ids and "发布" in texts:
        state = "POST_CONFIG"
        evidence.append("final_publish_button")
    elif (
        f"{TIKTOK}:id/pjg" in ids
        or f"{TIKTOK}:id/pje" in ids
    ) and "下一步" in texts:
        state = "EDIT"
        evidence.append("next_button")
    elif f"{TIKTOK}:id/viewpager_choose_media" in ids or (
        "最近项目" in texts and "视频" in descs and "照片" in descs
    ):
        state = "GALLERY"
        evidence.append("viewpager_choose_media")
    elif any("com.android.permissioncontroller:id/permission_" in rid for rid in ids):
        state = "PERMISSION"
        evidence.append("permissioncontroller")
    elif f"{TIKTOK}:id/upload_hot_area" in ids:
        state = "CREATE"
        evidence.append("upload_hot_area")
    elif (
        (
            f"{TIKTOK}:id/o70" in ids
            and ("首页" in texts or "主页" in texts or "创建" in descs)
        )
        or (
            "创建" in descs
            and ("首页" in texts or "首页" in descs)
            and ("主页" in texts or "主页" in descs)
        )
    ):
        state = "HOME"
        evidence.append("bottom_nav_create")

    return {
        "state": state,
        "evidence": evidence,
        "node_count": len(elements),
        "tiktok_visible": TIKTOK in packages,
        "packages": sorted(packages),
    }
