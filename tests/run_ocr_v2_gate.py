#!/usr/bin/env python3
"""Run Sprint V2 OCR instrumentation gates using durable on-device evidence."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT_EXEC = Path("/opt/y700/workspaces/y700-agent/bridge/root-exec.sh")
EVIDENCE_DIR = Path(
    "/proc/1/root/data/user/0/"
    "com.stanley.y700automation.test/files/ocr-v2-evidence"
)
RUNTIME_DIR = Path("/opt/y700/runtime/ocr-v2")
COMPONENT = (
    "com.stanley.y700automation.test/"
    "androidx.test.runner.AndroidJUnitRunner"
)

CASES = [
    (
        "com.stanley.y700automation.OcrV2ContractTest",
        [
            "substringSpecValidates",
            "boundedRegexValidates",
            "catastrophicRegexIsRejected",
            "regexAlternationIsRejected",
            "conflictingRoiIsRejected",
            "ocrFeatureFlagDefaultsOff",
            "ocrFeatureFlagCanBeExplicitlyEnabled",
        ],
        120,
    ),
    (
        "com.stanley.y700automation.vision.OcrTextLocatorNormalizationTest",
        [
            "stripsWhitespaceAndCaseFolds",
            "removesOnlyHanInternalOcrVerticalSeparator",
            "preservesLatinVerticalSeparator",
            "doesNotConfuseZeroWithLetterO",
            "doesNotConfuseOneWithLetterL",
            "inferenceContextExpandsToMinimumHeightWithoutChangingWidth",
            "inferenceContextClampsAtFrameBoundaryAndPreservesTargetHeight",
        ],
        120,
    ),
    (
        "com.stanley.y700automation.vision.OcrV2CacheAndTimeoutTest",
        [
            "staticFrameHitsCacheAndVisualChangeInvalidatesIt",
            "runtimeTimeoutMapsToStructuredOcrTimeoutAndDrainsInflight",
        ],
        180,
    ),
    (
        "com.stanley.y700automation.OcrV2RuntimeLifecycleTest",
        ["lazyLoadWarmReuseIdleUnloadAndReload"],
        180,
    ),
    (
        "com.stanley.y700automation.OcrV2StressTest",
        ["warmStressHasNoLoadUnloadChurnAndDocumentsResources"],
        600,
    ),
]


def simple_name(class_name: str) -> str:
    return class_name.rsplit(".", 1)[-1]


def evidence_path(class_name: str, method: str) -> Path:
    return EVIDENCE_DIR / f"test-{simple_name(class_name)}-{method}.json"


def run_instrumentation(class_name: str, timeout_sec: int) -> subprocess.CompletedProcess[str]:
    command = (
        f"toybox timeout {timeout_sec} /system/bin/su 2000 -c "
        f"'/system/bin/am instrument -w -r -e class {class_name} {COMPONENT}'"
    )
    return subprocess.run(
        [str(ROOT_EXEC), command],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout_sec + 60,
        check=False,
    )


def wait_for_evidence(
    class_name: str,
    methods: list[str],
    started_at_ms: int,
    wait_sec: int = 10,
) -> tuple[list[dict], list[str]]:
    deadline = time.monotonic() + wait_sec
    expected = [(method, evidence_path(class_name, method)) for method in methods]
    while time.monotonic() < deadline:
        if all(path.is_file() for _, path in expected):
            break
        time.sleep(0.25)

    rows: list[dict] = []
    errors: list[str] = []
    for method, path in expected:
        if not path.is_file():
            errors.append(f"missing evidence: {path.name}")
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"invalid evidence {path.name}: {exc}")
            continue
        if int(payload.get("started_at_ms") or 0) < started_at_ms - 1000:
            errors.append(f"stale evidence: {path.name}")
        if payload.get("class_name") != class_name:
            errors.append(f"class mismatch: {path.name}")
        if payload.get("method_name") != method:
            errors.append(f"method mismatch: {path.name}")
        if payload.get("status") != "PASS":
            errors.append(
                f"{path.name} status={payload.get('status')} "
                f"error={payload.get('error_message')}"
            )
        rows.append(payload)
    return rows, errors


def stress_report_errors() -> tuple[dict | None, list[str]]:
    path = EVIDENCE_DIR / "stress-report.json"
    if not path.is_file():
        return None, ["missing stress-report.json"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, [f"invalid stress-report.json: {exc}"]

    errors: list[str] = []
    warm = payload.get("warm") or {}
    if warm.get("runs") != 200:
        errors.append(f"stress runs expected 200, got {warm.get('runs')}")
    latency = warm.get("warm_latency_ms") or {}
    if latency.get("count") != 200:
        errors.append(
            f"warm latency count expected 200, got {latency.get('count')}"
        )
    runtime = warm.get("runtime_after_warm") or {}
    if runtime.get("in_flight") != 0:
        errors.append(
            f"stress runtime in_flight expected 0, got {runtime.get('in_flight')}"
        )
    return payload, errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--skip-stress",
        action="store_true",
        help="Run component gates but skip the 200-run stress gate.",
    )
    args = parser.parse_args()

    if not ROOT_EXEC.is_file():
        print(f"GATE_FAIL missing root executor: {ROOT_EXEC}", file=sys.stderr)
        return 2

    if EVIDENCE_DIR.exists():
        shutil.rmtree(EVIDENCE_DIR)

    started = datetime.now().astimezone()
    summary: dict = {
        "schema_version": 1,
        "started_at": started.isoformat(),
        "component": COMPONENT,
        "cases": [],
        "status": "PASS",
    }
    all_errors: list[str] = []

    for class_name, methods, timeout_sec in CASES:
        if args.skip_stress and class_name.endswith("OcrV2StressTest"):
            continue

        for method in methods:
            path = evidence_path(class_name, method)
            path.unlink(missing_ok=True)
        if class_name.endswith("OcrV2StressTest"):
            (EVIDENCE_DIR / "stress-report.json").unlink(missing_ok=True)

        started_at_ms = int(time.time() * 1000)
        try:
            proc = run_instrumentation(class_name, timeout_sec)
            command_error = None
        except subprocess.TimeoutExpired as exc:
            proc = None
            command_error = f"runner timeout after {timeout_sec + 60}s: {exc}"

        rows, errors = wait_for_evidence(class_name, methods, started_at_ms)
        if command_error:
            errors.append(command_error)
        if proc is not None and proc.returncode != 0:
            errors.append(
                f"root-exec rc={proc.returncode} stderr={proc.stderr.strip()}"
            )

        stress_report = None
        if class_name.endswith("OcrV2StressTest"):
            stress_report, stress_errors = stress_report_errors()
            errors.extend(stress_errors)

        case = {
            "class_name": class_name,
            "expected_methods": methods,
            "evidence": rows,
            "root_exec_returncode": None if proc is None else proc.returncode,
            "root_exec_stdout": "" if proc is None else proc.stdout[-4000:],
            "root_exec_stderr": "" if proc is None else proc.stderr[-4000:],
            "stress_report": stress_report,
            "status": "PASS" if not errors else "FAIL",
            "errors": errors,
        }
        summary["cases"].append(case)
        if errors:
            all_errors.extend(f"{simple_name(class_name)}: {e}" for e in errors)
            print(f"{simple_name(class_name)}: FAIL")
            for error in errors:
                print(f"  {error}")
        else:
            print(f"{simple_name(class_name)}: PASS ({len(rows)}/{len(methods)})")

    if all_errors:
        summary["status"] = "FAIL"
        summary["errors"] = all_errors

    summary["finished_at"] = datetime.now().astimezone().isoformat()
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = RUNTIME_DIR / f"ocr-v2-component-gate-{stamp}.json"
    temp = out.with_suffix(".json.tmp")
    temp.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    temp.replace(out)
    print(f"evidence={out}")
    print(f"GATE_{summary['status']}")
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
