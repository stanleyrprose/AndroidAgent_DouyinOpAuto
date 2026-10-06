#!/usr/bin/env python3
"""Run an allow-listed OCR V2 Android instrumentation class and verify durable evidence."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT_EXEC = Path("/opt/y700/workspaces/y700-agent/bridge/root-exec.sh")
EVIDENCE_DIR = Path(
    "/proc/1/root/data/user/0/"
    "com.stanley.y700automation/files/ocr-v2-evidence"
)
RUNNER = "com.stanley.y700automation.test/androidx.test.runner.AndroidJUnitRunner"

ALLOWED_CLASSES = {
    "com.stanley.y700automation.OcrV2ContractTest",
    "com.stanley.y700automation.vision.OcrTextLocatorNormalizationTest",
    "com.stanley.y700automation.vision.OcrV2CacheAndTimeoutTest",
    "com.stanley.y700automation.OcrV2RuntimeLifecycleTest",
    "com.stanley.y700automation.OcrV2ColdLatencyTest",
    "com.stanley.y700automation.OcrV2StressTest",
    "com.stanley.y700automation.vision.OcrV2RealDatasetBenchmarkTest",
}


def simple_name(class_name: str) -> str:
    return class_name.rsplit(".", 1)[-1]


def run_class(class_name: str, timeout_s: int) -> dict:
    if class_name not in ALLOWED_CLASSES:
        raise SystemExit(f"class is not allow-listed: {class_name}")
    if not ROOT_EXEC.is_file():
        raise SystemExit(f"root-exec not found: {ROOT_EXEC}")

    shutil.rmtree(EVIDENCE_DIR, ignore_errors=True)

    command = (
        f"toybox timeout {int(timeout_s)} "
        f"/data/local/y700-agent/workspaces/y700-agent/bridge/android-runtime-env.sh "
        f"/system/bin/su 2000 -c "
        f"'/system/bin/am instrument -w -r -e class {class_name} {RUNNER}'"
    )
    env = dict(os.environ)
    env["Y700_BRIDGE_TIMEOUT_MS"] = str((timeout_s + 30) * 1000)

    started = time.monotonic()
    proc = subprocess.run(
        [str(ROOT_EXEC), command],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout_s + 45,
        env=env,
    )
    duration_s = round(time.monotonic() - started, 3)

    prefix = f"test-{simple_name(class_name)}-"
    deadline = time.monotonic() + 10.0
    files: list[Path] = []
    while time.monotonic() < deadline:
        if EVIDENCE_DIR.is_dir():
            files = sorted(
                p
                for p in EVIDENCE_DIR.glob(f"{prefix}*.json")
                if p.is_file()
            )
        if files:
            break
        time.sleep(0.25)

    evidence = []
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            payload = {
                "status": "INVALID_EVIDENCE",
                "file": str(path),
                "error": repr(exc),
            }
        else:
            payload["file"] = str(path)
        evidence.append(payload)

    statuses = [item.get("status") for item in evidence]
    passed = (
        proc.returncode == 0
        and bool(evidence)
        and all(status == "PASS" for status in statuses)
    )

    result = {
        "schema_version": 1,
        "class_name": class_name,
        "status": "PASS" if passed else "FAIL",
        "instrumentation_exit_code": proc.returncode,
        "duration_s": duration_s,
        "evidence_count": len(evidence),
        "evidence": evidence,
        "stdout_tail": proc.stdout[-4000:],
        "stderr_tail": proc.stderr[-4000:],
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("class_name", choices=sorted(ALLOWED_CLASSES))
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    result = run_class(args.class_name, args.timeout)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        tmp = args.output.with_suffix(args.output.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, args.output)
    print(text, end="")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
