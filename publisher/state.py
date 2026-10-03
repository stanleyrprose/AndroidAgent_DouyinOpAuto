#!/usr/bin/env python3
import json
import sys
import xml.etree.ElementTree as ET

def detect_state(path):
    root = ET.parse(path).getroot()
    ids = set()
    texts = set()
    descs = set()
    packages = set()
    for node in root.iter("node"):
        rid = (node.attrib.get("resource-id") or "").strip()
        text = (node.attrib.get("text") or "").strip()
        desc = (node.attrib.get("content-desc") or "").strip()
        package = (node.attrib.get("package") or "").strip()
        if rid:
            ids.add(rid)
        if text:
            texts.add(text)
        if desc:
            descs.add(desc)
        if package:
            packages.add(package)

    state = "UNKNOWN"
    evidence = []

    # SystemUI can temporarily cover TikTok during a long automation step.
    if "com.android.systemui" in packages and (
        "com.android.systemui:id/keyguard_root_view" in ids
        or "com.android.systemui:id/device_entry_icon_fg" in ids
    ):
        state = "KEYGUARD"
        evidence.append("systemui_keyguard")
    elif "通过短信获取更新信息？" in texts and "com.zhiliaoapp.musically:id/e62" in ids:
        state = "SMS_PROMPT"
        evidence.append("sms_updates_prompt")
    # Foreground overlays can coexist with background nodes in uiautomator XML.
    elif "谁可以看" in texts and "仅自己" in texts:
        state = "VISIBILITY"
        evidence.append("visibility_sheet")
    elif "com.zhiliaoapp.musically:id/st6" in ids and "发布" in texts:
        state = "POST_CONFIG"
        evidence.append("final_publish_button")
    elif "com.zhiliaoapp.musically:id/pjg" in ids and "下一步" in texts:
        state = "EDIT"
        evidence.append("next_button")
    elif "com.zhiliaoapp.musically:id/viewpager_choose_media" in ids or (
        "最近项目" in texts and "视频" in descs and "照片" in descs
    ):
        state = "GALLERY"
        evidence.append("viewpager_choose_media")
    elif any("com.android.permissioncontroller:id/permission_" in rid for rid in ids):
        state = "PERMISSION"
        evidence.append("permissioncontroller")
    elif "com.zhiliaoapp.musically:id/upload_hot_area" in ids:
        state = "CREATE"
        evidence.append("upload_hot_area")
    elif "com.zhiliaoapp.musically:id/o70" in ids and (
        "首页" in texts or "主页" in texts or "创建" in descs
    ):
        state = "HOME"
        evidence.append("bottom_nav_create")

    return {
        "state": state,
        "evidence": evidence,
        "node_count": sum(1 for _ in root.iter("node")),
        "tiktok_visible": "com.zhiliaoapp.musically" in packages,
        "packages": sorted(packages),
    }

def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: state.py <ui.xml>")
    print(json.dumps(detect_state(sys.argv[1]), ensure_ascii=False))

if __name__ == "__main__":
    main()
