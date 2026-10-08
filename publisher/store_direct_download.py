#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import time
from pathlib import Path

try:
    from .job_contract import write_json_atomic
except ImportError:
    from job_contract import write_json_atomic

ROOT = Path(__file__).resolve().parents[1]
PULL_ROOT = Path(os.environ.get("Y700_DIRECT_PULL_ROOT", "/opt/y700/runtime/direct-download"))
HOST_PULL_ROOT = os.environ.get("Y700_DIRECT_HOST_PULL_ROOT", "/data/local/y700-agent/runtime/direct-download")
RUN_ROOT = Path(os.environ.get("Y700_DIRECT_RUN_ROOT", "/opt/y700/runtime/direct-download-runs"))
STATE = Path(os.environ.get("Y700_DIRECT_STATE", "/opt/y700/runtime/state/direct-download.json"))
ROOT_EXEC = Path(os.environ.get("Y700_ROOT_EXEC", str(ROOT / "bridge" / "root-exec.sh")))
ANDROIDCTL = Path(os.environ.get("Y700_ANDROIDCTL", str(ROOT / "bridge" / "androidctl.sh")))
SECURE_UNLOCK = Path(os.environ.get("Y700_SECURE_UNLOCK", str(ROOT / "bridge" / "secure-unlock.sh")))
DEFAULT_ALBUM = "Y700Agent"
ALBUM_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
JOB_RE = re.compile(r"^dd-[0-9]{5,32}$")


class DirectStoreError(RuntimeError):
    pass


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def run(cmd, *, check=True, timeout=30, env=None):
    try:
        p = subprocess.run(
            [str(x) for x in cmd],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        raise DirectStoreError(f"command timed out after {timeout}s") from exc
    if check and p.returncode != 0:
        raise DirectStoreError(f"command failed rc={p.returncode}: {p.stderr.strip()}")
    return p


def root_exec(command: str, *, check=True, timeout_ms=30000):
    env = os.environ.copy()
    env["Y700_BRIDGE_TIMEOUT_MS"] = str(int(timeout_ms))
    return run(
        [ROOT_EXEC, command],
        check=check,
        timeout=max(5.0, timeout_ms / 1000 + 5.0),
        env=env,
    )


def normalize_power_state(raw: str) -> str:
    if "mWakefulness=Asleep" in raw:
        return "ASLEEP"
    if "mWakefulness=Awake" in raw:
        return "AWAKE"
    return "UNKNOWN"


def capture_power_state() -> tuple[str, str]:
    p = run([ANDROIDCTL, "screen-state"], check=False, timeout=15)
    raw = p.stdout.strip() if isinstance(p.stdout, str) else ""
    return normalize_power_state(raw), raw[:400]


def restore_power_state(initial: str) -> dict:
    if initial != "ASLEEP":
        return {"status": "RESTORE_NOT_REQUIRED", "initial_power_state": initial}
    root_exec("input keyevent KEYCODE_SLEEP", timeout_ms=10000)
    return {
        "status": "RESTORED_ASLEEP",
        "initial_power_state": "ASLEEP",
        "restore_action": "KEYCODE_SLEEP",
        "restored_at": now_iso(),
    }


def load_direct_manifest(job_id: str) -> dict:
    job = PULL_ROOT / job_id
    if not (job / ".complete").is_file():
        raise DirectStoreError(f"direct artifact bundle not complete: {job_id}")
    data = json.load(open(job / "manifest.json", encoding="utf-8"))
    if data.get("schema_version") != 1 or data.get("kind") != "generic-artifact":
        raise DirectStoreError("invalid direct artifact manifest")
    if data.get("job_id") != job_id:
        raise DirectStoreError("job_id mismatch")
    artifacts = data.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 1:
        raise DirectStoreError("direct download requires exactly one artifact")
    if artifacts[0].get("name") != "original.mp4":
        raise DirectStoreError("direct download artifact must be original.mp4")
    return data


def existing_result(job_id: str) -> dict | None:
    path = RUN_ROOT / job_id / "result.json"
    if not path.is_file():
        return None
    try:
        data = json.load(open(path, encoding="utf-8"))
    except Exception:
        return None
    if data.get("job_id") == job_id and data.get("status") == "DIRECT_DOWNLOADED":
        return data
    return None


def store(job_id: str, album: str = DEFAULT_ALBUM) -> dict:
    if not JOB_RE.fullmatch(job_id):
        raise DirectStoreError("invalid direct-download job id")
    if not ALBUM_RE.fullmatch(album):
        raise DirectStoreError("invalid album name")
    previous = existing_result(job_id)
    if previous:
        return {**previous, "idempotent": True}

    load_direct_manifest(job_id)
    run_dir = RUN_ROOT / job_id
    run_dir.mkdir(parents=True, exist_ok=True)
    initial, raw = capture_power_state()
    write_json_atomic(run_dir / "initial-power-state.json", {
        "schema_version": 1,
        "job_id": job_id,
        "initial_power_state": initial,
        "captured_at": now_iso(),
        "raw_screen_state": raw,
    })
    write_json_atomic(STATE, {
        "status": "UNLOCKING_FOR_DIRECT_DOWNLOAD",
        "job_id": job_id,
        "album": album,
        "initial_power_state": initial,
        "timestamp": now_iso(),
    })

    try:
        run(["bash", SECURE_UNLOCK], timeout=45)
        src = f"{HOST_PULL_ROOT}/{job_id}/original.mp4"
        album_dir = f"/sdcard/Movies/{album}"
        display_name = f"{job_id}.mp4"
        dst = f"{album_dir}/{display_name}"
        part = f"{album_dir}/.{display_name}.part"
        root_exec(
            f"mkdir -p {shlex.quote(album_dir)}; "
            f"cp {shlex.quote(src)} {shlex.quote(part)}; "
            f"chmod 644 {shlex.quote(part)}; "
            f"mv -f {shlex.quote(part)} {shlex.quote(dst)}",
            timeout_ms=30000,
        )
        root_exec(
            f"am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file://{dst} >/dev/null",
            timeout_ms=10000,
        )

        relative_path = f"Movies/{album}/"
        query = (
            "content query --uri content://media/external/video/media "
            "--projection _id:_display_name:relative_path "
            f"--where \"_display_name='{display_name}' AND relative_path='{relative_path}'\""
        )
        for _ in range(30):
            q = root_exec(query, check=False, timeout_ms=5000)
            text = q.stdout or ""
            if display_name in text and relative_path in text:
                break
            time.sleep(1)
        else:
            raise DirectStoreError("MediaStore scan timeout")

        result = {
            "status": "DIRECT_DOWNLOADED",
            "job_id": job_id,
            "album": album,
            "device_path": dst,
            "media_store_verified": True,
            "note_saved": False,
            "stored_at": now_iso(),
            "initial_power_state": initial,
        }
        write_json_atomic(run_dir / "result.json", result)
        write_json_atomic(STATE, {**result, "timestamp": now_iso()})
        return result
    finally:
        try:
            power = restore_power_state(initial)
            write_json_atomic(run_dir / "power-restore.json", power)
        except Exception as exc:
            write_json_atomic(run_dir / "power-restore.json", {
                "status": "POWER_RESTORE_FAILED",
                "initial_power_state": initial,
                "reason": str(exc),
                "timestamp": now_iso(),
            })


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("job_id")
    ap.add_argument("--album", default=DEFAULT_ALBUM)
    args = ap.parse_args()
    try:
        result = store(args.job_id, args.album)
    except Exception as exc:
        print(json.dumps({
            "status": "DIRECT_DOWNLOAD_FAILED",
            "job_id": args.job_id,
            "reason": str(exc),
        }, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
