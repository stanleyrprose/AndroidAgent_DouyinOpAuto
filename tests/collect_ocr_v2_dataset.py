#!/usr/bin/env python3
"""Collect a runtime-private real-app OCR benchmark dataset on Y700.

The dataset lives under /opt/y700/runtime and is never committed. Ground truth
comes from the live accessibility tree only for benchmark scoring; production
OCR does not depend on semantic metadata.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

ROOT_EXEC = Path("/opt/y700/workspaces/y700-agent/bridge/root-exec.sh")
CHROOT_DIR = Path("/opt/y700/runtime/ocr-v2-dataset")
HOST_DIR = "/data/local/y700-agent/runtime/ocr-v2-dataset"
TARGET_PACKAGE = "com.stanley.y700automation"
MAX_TARGETS_PER_SCREEN = 18

SCREENS = [
    ("settings_wifi", "am start -a android.settings.WIFI_SETTINGS", "WLAN"),
    ("settings_display", "am start -a android.settings.DISPLAY_SETTINGS", "显示和亮度"),
    ("settings_sound", "am start -a android.settings.SOUND_SETTINGS", "声音和振动"),
    ("settings_apps", "am start -a android.settings.APPLICATION_SETTINGS", "所有应用"),
    ("settings_battery", "am start -a android.settings.BATTERY_SAVER_SETTINGS", "省电模式"),
    ("settings_security", "am start -a android.settings.SECURITY_SETTINGS", "安全"),
]

BOUNDS_RE = re.compile(r"^\[(\d+),(\d+)\]\[(\d+),(\d+)\]$")


def root_shell(command: str, *, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["Y700_BRIDGE_TIMEOUT_MS"] = "60000"
    return subprocess.run(
        [str(ROOT_EXEC), command],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
        env=env,
    )


def parse_bounds(raw: str):
    m = BOUNDS_RE.match(raw or "")
    if not m:
        return None
    x1, y1, x2, y2 = map(int, m.groups())
    if x2 <= x1 or y2 <= y1:
        return None
    return [x1, y1, x2, y2]


def script_for(text: str) -> str:
    for ch in text:
        cp = ord(ch)
        if 0x3400 <= cp <= 0x9FFF or 0xF900 <= cp <= 0xFAFF:
            return "chinese"
    return "latin"


def normalized(text: str) -> str:
    return re.sub(r"\s+", "", text).casefold()


def expanded_roi(bbox, width: int, height: int):
    x1, y1, x2, y2 = bbox
    w = x2 - x1
    h = y2 - y1
    pad_x = max(48, int(w * 0.55))
    pad_y = max(48, int(h * 1.15))
    return [
        max(0, x1 - pad_x),
        max(0, y1 - pad_y),
        min(width, x2 + pad_x),
        min(height, y2 + pad_y),
    ]


def get_display_size():
    out = root_shell("wm size").stdout
    m = re.search(r"(?:Physical|Override) size:\s*(\d+)x(\d+)", out)
    if not m:
        raise RuntimeError(f"unable to parse wm size: {out!r}")
    return int(m.group(1)), int(m.group(2))


def choose_targets(xml_path: Path, width: int, height: int):
    root = ET.parse(xml_path).getroot()
    candidates = []
    seen = set()
    for node in root.iter("node"):
        text = (node.attrib.get("text") or "").strip()
        bbox = parse_bounds(node.attrib.get("bounds", ""))
        if not text or bbox is None:
            continue
        norm = normalized(text)
        if len(norm) < 2 or len(norm) > 40:
            continue
        if norm in seen:
            continue
        x1, y1, x2, y2 = bbox
        bw, bh = x2 - x1, y2 - y1
        if bw < 28 or bh < 20:
            continue
        if bw * bh > width * height * 0.20:
            continue
        if y1 < 0 or x1 < 0 or x2 > width or y2 > height:
            continue
        seen.add(norm)
        candidates.append(
            {
                "text": text,
                "bbox": bbox,
                "roi": expanded_roi(bbox, width, height),
                "script": script_for(text),
                "resource_id": node.attrib.get("resource-id", ""),
                "class": node.attrib.get("class", ""),
            }
        )

    # Prefer a spatially diverse deterministic subset.
    candidates.sort(key=lambda x: (x["bbox"][1], x["bbox"][0], x["text"]))
    if len(candidates) <= MAX_TARGETS_PER_SCREEN:
        return candidates
    selected = []
    for i in range(MAX_TARGETS_PER_SCREEN):
        idx = round(i * (len(candidates) - 1) / (MAX_TARGETS_PER_SCREEN - 1))
        selected.append(candidates[idx])
    return selected


def stage_into_target(files):
    root_shell(
        f"run-as {TARGET_PACKAGE} sh -c 'rm -rf files/ocr-v2-dataset; "
        "mkdir -p files/ocr-v2-dataset'"
    )
    for src in files:
        name = src.name.replace("'", "")
        host_src = f"{HOST_DIR}/{name}"
        cmd = (
            f"cat '{host_src}' | run-as {TARGET_PACKAGE} sh -c "
            f"'cat > files/ocr-v2-dataset/{name}'"
        )
        root_shell(cmd)


def xml_texts(path: Path):
    root = ET.parse(path).getroot()
    return {
        (node.attrib.get("text") or "").strip()
        for node in root.iter("node")
        if (node.attrib.get("text") or "").strip()
    }


def capture_screen(screen_id: str, launch: str, anchor: str, retries: int = 3):
    xml_host = f"{HOST_DIR}/{screen_id}.xml"
    png_host = f"{HOST_DIR}/{screen_id}.png"
    before_host = f"{HOST_DIR}/{screen_id}.before.xml"
    after_host = f"{HOST_DIR}/{screen_id}.after.xml"
    png_tmp_host = f"{HOST_DIR}/{screen_id}.png.tmp"
    launch_wait = launch.replace("am start ", "am start -W ", 1)

    final_xml = CHROOT_DIR / f"{screen_id}.xml"
    final_png = CHROOT_DIR / f"{screen_id}.png"
    before_xml = CHROOT_DIR / f"{screen_id}.before.xml"
    after_xml = CHROOT_DIR / f"{screen_id}.after.xml"
    png_tmp = CHROOT_DIR / f"{screen_id}.png.tmp"

    for attempt in range(1, retries + 1):
        command = (
            "set -e; "
            f"mkdir -p '{HOST_DIR}'; "
            f"rm -f '{xml_host}' '{png_host}' '{before_host}' '{after_host}' '{png_tmp_host}'; "
            "input keyevent KEYCODE_WAKEUP >/dev/null 2>&1 || true; "
            "wm dismiss-keyguard >/dev/null 2>&1 || true; "
            f"{launch_wait} >/dev/null 2>&1; "
            "sleep 2; "
            f"uiautomator dump --compressed '{before_host}' >/dev/null 2>&1; "
            f"test -s '{before_host}'; "
            f"screencap -p '{png_tmp_host}'; "
            f"test -s '{png_tmp_host}'; "
            f"uiautomator dump --compressed '{after_host}' >/dev/null 2>&1; "
            f"test -s '{after_host}'"
        )
        result = root_shell(command, check=False)
        if result.returncode != 0:
            print(
                f"{screen_id}: capture retry {attempt}/{retries} "
                f"rc={result.returncode}"
            )
            continue

        try:
            before = {normalized(text) for text in xml_texts(before_xml)}
            after = {normalized(text) for text in xml_texts(after_xml)}
        except Exception as exc:
            print(f"{screen_id}: capture retry {attempt}/{retries} xml={exc}")
            continue

        anchor_norm = normalized(anchor)
        before_anchor = any(anchor_norm in text for text in before)
        after_anchor = any(anchor_norm in text for text in after)
        denominator = max(1, min(len(before), len(after)))
        overlap = len(before & after) / denominator

        if not before_anchor or not after_anchor or overlap < 0.70:
            print(
                f"{screen_id}: capture retry {attempt}/{retries} "
                f"anchor_before={before_anchor} anchor_after={after_anchor} "
                f"overlap={overlap:.3f}"
            )
            continue

        after_xml.replace(final_xml)
        png_tmp.replace(final_png)
        before_xml.unlink(missing_ok=True)
        return xml_host, png_host, overlap

    raise RuntimeError(f"{screen_id}: unable to capture stable anchored screen")


def main():
    CHROOT_DIR.mkdir(parents=True, exist_ok=True)
    width, height = get_display_size()
    screens = []

    for screen_id, launch, anchor in SCREENS:
        _, _, stability_overlap = capture_screen(screen_id, launch, anchor)
        xml_path = CHROOT_DIR / f"{screen_id}.xml"
        png_path = CHROOT_DIR / f"{screen_id}.png"
        targets = choose_targets(xml_path, width, height)
        screens.append(
            {
                "id": screen_id,
                "image": png_path.name,
                "width": width,
                "height": height,
                "capture_anchor": anchor,
                "stability_overlap": stability_overlap,
                "targets": targets,
            }
        )
        print(
            f"{screen_id}: {len(targets)} targets "
            f"({sum(t['script']=='chinese' for t in targets)} chinese / "
            f"{sum(t['script']=='latin' for t in targets)} latin)"
        )

    manifest = {
        "schema_version": 1,
        "runtime_private": True,
        "created_at": datetime.now().astimezone().isoformat(),
        "device": "Lenovo TB323FU",
        "display": [width, height],
        "screens": screens,
        "target_count": sum(len(s["targets"]) for s in screens),
    }
    manifest_path = CHROOT_DIR / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    stage_files = [manifest_path]
    stage_files.extend(CHROOT_DIR / s["image"] for s in screens)
    stage_into_target(stage_files)
    print(f"manifest={manifest_path}")
    print(f"target_count={manifest['target_count']}")
    print("staged_to_target_app=true")


if __name__ == "__main__":
    main()
