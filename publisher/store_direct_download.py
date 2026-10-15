#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
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
HOST_MEDIA_ROOT = Path(os.environ.get("Y700_DIRECT_HOST_MEDIA_ROOT", "/proc/1/root/data/media/0"))
RUN_ROOT = Path(os.environ.get("Y700_DIRECT_RUN_ROOT", "/opt/y700/runtime/direct-download-runs"))
STATE = Path(os.environ.get("Y700_DIRECT_STATE", "/opt/y700/runtime/state/direct-download.json"))
ROOT_EXEC = Path(os.environ.get("Y700_ROOT_EXEC", str(ROOT / "bridge" / "root-exec.sh")))
ANDROIDCTL = Path(os.environ.get("Y700_ANDROIDCTL", str(ROOT / "bridge" / "androidctl.sh")))
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
    # Direct-download has no UI step; do not wake, unlock, or sleep the device.
    return {"status": "NO_SCREEN_MUTATION", "initial_power_state": initial}


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


def verified_album_file(job_id: str, album: str, artifact: dict) -> bool:
    """Read-only reconciliation of Android's backing media file."""
    file = HOST_MEDIA_ROOT / "Movies" / album / f"{job_id}.mp4"
    if not file.exists():
        return False
    if file.is_symlink() or not file.is_file():
        raise DirectStoreError("unsafe existing album file")
    if file.stat().st_size != artifact["size"]:
        raise DirectStoreError("existing album file size mismatch; refusing overwrite")
    expected = str(artifact["sha256"]).lower()
    digest = hashlib.sha256()
    with file.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != expected:
        raise DirectStoreError("existing album file SHA-256 mismatch; refusing overwrite")
    return True


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
    manifest = load_direct_manifest(job_id)
    artifact = manifest["artifacts"][0]
    present = verified_album_file(job_id, album, artifact)
    previous = existing_result(job_id)
    if previous:
        if not present or previous.get("album") != album:
            raise DirectStoreError("previous success receipt does not match existing album media")
        return {**previous, "idempotent": True}

    run_dir = RUN_ROOT / job_id
    run_dir.mkdir(parents=True, exist_ok=True)
    try:
        initial, raw = capture_power_state()
    except (OSError, DirectStoreError) as exc:
        initial, raw = "UNKNOWN", f"screen_state_unavailable:{type(exc).__name__}"
    write_json_atomic(run_dir / "initial-power-state.json", {
        "schema_version": 1,
        "job_id": job_id,
        "initial_power_state": initial,
        "captured_at": now_iso(),
        "raw_screen_state": raw,
    })
    write_json_atomic(STATE, {
        "status": "VERIFYING_DIRECT_DOWNLOAD",
        "job_id": job_id,
        "album": album,
        "initial_power_state": initial,
        "timestamp": now_iso(),
    })

    try:
        # Direct file storage uses Android host shell, not an interactive UI.
        # Unlocking an asleep screen is unnecessary and can fail before the copy.
        src = f"{HOST_PULL_ROOT}/{job_id}/original.mp4"
        album_dir = f"/sdcard/Movies/{album}"
        display_name = f"{job_id}.mp4"
        dst = f"{album_dir}/{display_name}"
        part = f"{album_dir}/.{display_name}.part"
        if not present:
            root_exec(
                f"mkdir -p {shlex.quote(album_dir)}; "
                f"cp {shlex.quote(src)} {shlex.quote(part)}; "
                f"chmod 644 {shlex.quote(part)}; "
                f"mv -f {shlex.quote(part)} {shlex.quote(dst)}",
                timeout_ms=30000,
            )
        if present:
            write_json_atomic(run_dir / "file-verification.json", {
                "status": "FILE_SHA256_VERIFIED",
                "job_id": job_id,
                "album": album,
                "size": artifact["size"],
                "sha256": artifact["sha256"],
                "verified_at": now_iso(),
            })

        relative_path = f"Movies/{album}/"
        query = (
            "content query --uri content://media/external/video/media "
            "--projection _id:_display_name:relative_path "
            f"--where \"_display_name='{display_name}' AND relative_path='{relative_path}'\""
        )
        indexed = False
        # For an existing file, query first; don't trigger another scan unless
        # the MediaStore row is absent. Neither path re-copies the video.
        for attempt in range(10):
            try:
                q = root_exec(query, check=False, timeout_ms=5000)
                indexed = display_name in (q.stdout or "") and relative_path in (q.stdout or "")
            except DirectStoreError:
                indexed = False
            if indexed:
                break
            if attempt == 0:
                try:
                    root_exec(
                        f"am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file://{dst} >/dev/null",
                        timeout_ms=10000,
                    )
                except DirectStoreError:
                    pass
            time.sleep(1)
        if not indexed:
            raise DirectStoreError("album file may exist, but MediaStore verification is pending")

        result = {
            "status": "DIRECT_DOWNLOADED",
            "job_id": job_id,
            "album": album,
            "device_path": dst,
            "media_store_verified": True,
            "reconciled_existing_file": present,
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
