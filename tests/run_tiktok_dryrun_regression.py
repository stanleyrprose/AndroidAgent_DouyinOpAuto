#!/usr/bin/env python3
"""Real-Y700 TikTok cold-start DRY_RUN regression gate.

Stages the selected READY media once, then repeats only the UI/controller path:
force-stop -> cold launch -> gallery -> media -> caption -> PRIVATE ->
publish button reachable -> evidence. The generic controller exposes no COMMIT.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.tiktok import controller as tiktok
from publisher.job_contract import load_manifest
from publisher.publish_job import load_metadata, read_text

READY = Path("/opt/y700/media/ready")
UI_JOBS = Path(os.environ.get("Y700_UI_JOBS", "/opt/y700/ui-jobs"))
DEFAULT_OUTPUT = Path("/opt/y700/runtime/tiktok-regression/v05-cold-dryrun.jsonl")


def git_head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def append_record(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())


def read_records(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def workflow_metrics(workflow_job_id: str | None) -> dict:
    if not workflow_job_id:
        return {}
    path = UI_JOBS / workflow_job_id / "result.json"
    if not path.is_file():
        return {"ui_result_missing": True}
    data = json.loads(path.read_text(encoding="utf-8"))
    actions = data.get("actions") or []
    latencies = {
        str(a.get("action_id")): a.get("latency_ms")
        for a in actions
        if a.get("action_id")
    }
    numeric = [v for v in latencies.values() if isinstance(v, (int, float))]
    return {
        "ui_status": data.get("status"),
        "host_duration_ms": data.get("host_duration_ms"),
        "home_create_ms": latencies.get("home-create"),
        "max_action_ms": max(numeric) if numeric else None,
        "action_latencies_ms": latencies,
    }


def summary(path: Path, expected_commit: str | None = None) -> dict:
    rows = read_records(path)
    if expected_commit:
        rows = [r for r in rows if str(r.get("commit", "")).startswith(expected_commit)]
    passed = sum(1 for r in rows if r.get("status") == "PASS")
    total = len(rows)
    required = math.ceil(total * 0.95) if total else 0
    durations = [
        r.get("host_duration_ms")
        for r in rows
        if isinstance(r.get("host_duration_ms"), (int, float))
    ]
    home = [
        r.get("home_create_ms")
        for r in rows
        if isinstance(r.get("home_create_ms"), (int, float))
    ]
    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": (passed / total) if total else 0.0,
        "required_passes_at_95pct": required,
        "gate_pass": total >= 20 and passed >= 19,
        "max_host_duration_ms": max(durations) if durations else None,
        "max_home_create_ms": max(home) if home else None,
        "output": str(path),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("job_id")
    ap.add_argument("--count", type=int, default=20)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--expected-commit")
    ap.add_argument("--skip-stage", action="store_true")
    args = ap.parse_args()

    head = git_head()
    if args.expected_commit and not head.startswith(args.expected_commit):
        raise SystemExit(
            f"commit mismatch: expected {args.expected_commit}, actual {head}"
        )
    if args.count < 1 or args.offset < 0:
        raise SystemExit("count must be >=1 and offset >=0")

    job = READY / args.job_id
    manifest = load_manifest(job / "manifest.json")
    if manifest["job_id"] != args.job_id:
        raise SystemExit("job_id mismatch")
    if manifest["publish_mode"] != "DRY_RUN":
        raise SystemExit("regression gate requires publish_mode=DRY_RUN")

    metadata = load_metadata(job, manifest)
    caption = read_text(job / manifest["caption_file"])
    title = str(metadata.get("title", manifest.get("title", ""))).strip()
    visibility = str(
        metadata.get("visibility", manifest.get("visibility", "PRIVATE"))
    ).strip().upper()
    if visibility != "PRIVATE":
        raise SystemExit("regression gate requires PRIVATE visibility")

    existing = read_records(args.output)
    existing_indexes = {
        int(r["run_index"])
        for r in existing
        if str(r.get("commit", "")).startswith(head)
        and isinstance(r.get("run_index"), int)
    }
    requested_indexes = set(range(args.offset + 1, args.offset + args.count + 1))
    overlap = sorted(existing_indexes & requested_indexes)
    if overlap:
        raise SystemExit(f"run indexes already recorded for this commit: {overlap}")

    if not args.skip_stage:
        subprocess.run(
            [sys.executable, str(ROOT / "publisher" / "stage_job.py"), args.job_id],
            cwd=ROOT,
            check=True,
        )

    for run_index in range(args.offset + 1, args.offset + args.count + 1):
        started = time.monotonic()
        record = {
            "run_index": run_index,
            "commit": head,
            "job_id": args.job_id,
            "publish_mode": "DRY_RUN",
            "visibility": "PRIVATE",
            "started_at_epoch": time.time(),
        }
        try:
            result = tiktok.prepare_dry_run(
                caption,
                title=title,
                visibility=visibility,
                album="Y700Agent",
            )
            record.update(
                {
                    "status": "PASS",
                    "workflow_job_id": result.get("workflow_job_id"),
                    "evidence": (result.get("evidence") or {}).get("source_path"),
                }
            )
        except Exception as exc:
            record.update(
                {
                    "status": "FAIL",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
            result_obj = getattr(exc, "result", None)
            if isinstance(result_obj, dict):
                record["workflow_job_id"] = result_obj.get("job_id")
                record["workflow_error"] = result_obj.get("error")
        finally:
            tiktok.force_stop()

        record["wall_duration_s"] = round(time.monotonic() - started, 3)
        record.update(workflow_metrics(record.get("workflow_job_id")))
        append_record(args.output, record)
        print(json.dumps(record, ensure_ascii=False), flush=True)

    report = summary(args.output, args.expected_commit or head)
    print(json.dumps({"summary": report}, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
