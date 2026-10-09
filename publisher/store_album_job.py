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
    from .job_contract import load_manifest, write_json_atomic
except ImportError:
    from job_contract import load_manifest, write_json_atomic

if str(Path(__file__).resolve().parents[1]) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(Path(__file__).resolve().parents[1]))
from automation import resource_arbiter, state_integrity

ROOT = Path(__file__).resolve().parents[1]
READY = Path(os.environ.get("Y700_READY_ROOT", "/opt/y700/media/ready"))
STATE = Path(os.environ.get("Y700_ALBUM_STORE_STATE", "/opt/y700/runtime/state/album-store.json"))
RUN_ROOT = Path(os.environ.get("Y700_ALBUM_STORE_RUN_ROOT", "/opt/y700/runtime/album-store"))
HOST_READY = os.environ.get("Y700_HOST_READY_ROOT", "/data/local/y700-agent/media/ready")
ROOT_EXEC = Path(os.environ.get("Y700_ROOT_EXEC", str(ROOT / "bridge" / "root-exec.sh")))
ANDROIDCTL = Path(os.environ.get("Y700_ANDROIDCTL", str(ROOT / "bridge" / "androidctl.sh")))
SECURE_UNLOCK = Path(os.environ.get("Y700_SECURE_UNLOCK", str(ROOT / "bridge" / "secure-unlock.sh")))
DEFAULT_ALBUM = "Y700Agent"
ALBUM_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class AlbumStoreError(RuntimeError):
    pass


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def write_state(status: str, job_id: str, **extra) -> dict:
    data = {"status": status, "job_id": job_id, "timestamp": now_iso(), **extra}
    write_json_atomic(STATE, data)
    return data


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
        raise AlbumStoreError(f"command timed out after {timeout}s") from exc
    if check and p.returncode != 0:
        raise AlbumStoreError(f"command failed rc={p.returncode}: {p.stderr.strip()}")
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


def save_caption_note(job: Path, manifest: dict, run_dir: Path) -> dict:
    caption_name = str(manifest["caption_file"])
    caption_path = job / caption_name
    if not caption_path.is_file():
        raise AlbumStoreError(f"missing caption file: {caption_name}")
    caption = caption_path.read_text(encoding="utf-8").strip()
    if not caption:
        raise AlbumStoreError("caption is empty")

    caption_sha256 = hashlib.sha256(caption.encode("utf-8")).hexdigest()
    marker = run_dir / "note-result.json"
    if marker.is_file():
        try:
            previous = json.load(open(marker, encoding="utf-8"))
        except Exception:
            previous = {}
        if (
            previous.get("note_saved") is True
            and previous.get("caption_sha256") == caption_sha256
            and previous.get("note_app") == "com.zui.notes"
        ):
            return {**previous, "idempotent": True}

    q_caption = shlex.quote(caption)
    command = (
        "am start -W "
        "-n com.zui.notes/.home.ShareReceiverIntentActivity "
        "-a android.intent.action.SEND -t text/plain "
        f"--es android.intent.extra.TEXT {q_caption}"
    )
    started = root_exec(command, timeout_ms=15000)
    output = (started.stdout or "") + "\n" + (started.stderr or "")
    if "Status: ok" not in output or "com.zui.notes/.home.MainActivity" not in output:
        raise AlbumStoreError("ZUI Notes share receiver did not open MainActivity")

    # ZUI Notes persists shared text when the editor lifecycle is completed.
    # This behavior was verified on the target Y700 against notes_v2.
    time.sleep(0.8)
    root_exec("input keyevent KEYCODE_BACK", timeout_ms=10000)
    time.sleep(0.8)

    result = {
        "note_saved": True,
        "note_app": "com.zui.notes",
        "note_method": "ACTION_SEND_TEXT_PLAIN",
        "caption_sha256": caption_sha256,
        "saved_at": now_iso(),
    }
    write_json_atomic(marker, result)
    return result


def existing_result(job_id: str) -> dict | None:
    path = RUN_ROOT / job_id / "result.json"
    if not path.is_file():
        return None
    try:
        data = json.load(open(path, encoding="utf-8"))
    except Exception:
        return None
    if (
        data.get("job_id") == job_id
        and data.get("status") == "STORED_IN_ALBUM"
        and data.get("note_saved") is True
    ):
        return data
    return None


def store(job_id: str, album: str = DEFAULT_ALBUM) -> dict:
    if not ALBUM_RE.fullmatch(album):
        raise AlbumStoreError("invalid album name")
    previous = existing_result(job_id)
    if previous:
        return {**previous, "idempotent": True}

    job = READY / job_id
    if not job.is_dir():
        raise AlbumStoreError(f"job not READY: {job_id}")
    manifest = load_manifest(job / "manifest.json")
    if manifest["job_id"] != job_id:
        raise AlbumStoreError("job_id mismatch")

    run_dir = RUN_ROOT / job_id
    run_dir.mkdir(parents=True, exist_ok=True)
    marker = run_dir / "initial-power-state.json"
    initial, raw = capture_power_state()
    write_json_atomic(marker, {
        "schema_version": 1,
        "job_id": job_id,
        "initial_power_state": initial,
        "captured_at": now_iso(),
        "raw_screen_state": raw,
    })

    write_state("UNLOCKING_FOR_ALBUM_STORE", job_id, album=album, initial_power_state=initial)
    try:
        claim_cm = resource_arbiter.acquire_android_ui(
            owner_kind="LEGACY",
            owner_id=f"legacy:store-album:{job_id}",
            backend_type="store-album",
            backend_job_id=job_id,
            request_sha256=resource_arbiter.request_identity(
                {"intent": "STORE_ALBUM", "job_id": job_id, "album": album}
            ),
            timeout_sec=30.0,
        )
        claim_cm.__enter__()
    except resource_arbiter.ResourceError as exc:
        raise AlbumStoreError(str(exc)) from exc

    result = None
    error = None
    try:
        # STORE_ALBUM is still a legacy UI workflow. Before its first raw UI
        # mutation, invalidate all prior state tokens while holding the same
        # canonical android_ui ownership used by Core v2.
        state_integrity.bump_epoch(f"LEGACY_STORE_ALBUM_UI:{job_id}")
        run(["bash", SECURE_UNLOCK], timeout=45)
        write_state("STORING_IN_ALBUM", job_id, album=album, initial_power_state=initial)

        video = str(manifest["video_file"])
        src = f"{HOST_READY}/{job_id}/{video}"
        album_dir = f"/sdcard/Movies/{album}"
        display_name = f"{job_id}.mp4"
        dst = f"{album_dir}/{display_name}"
        part = f"{album_dir}/.{display_name}.part"
        q_album = shlex.quote(album_dir)
        q_src = shlex.quote(src)
        q_part = shlex.quote(part)
        q_dst = shlex.quote(dst)
        # Non-destructive by contract: only this job's deterministic destination
        # may be replaced. Other files in the album are never removed.
        root_exec(
            f"mkdir -p {q_album}; cp {q_src} {q_part}; chmod 644 {q_part}; mv -f {q_part} {q_dst}",
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
        media_row = ""
        for _ in range(30):
            q = root_exec(query, check=False, timeout_ms=5000)
            media_row = q.stdout or ""
            if display_name in media_row and relative_path in media_row:
                break
            time.sleep(1)
        else:
            raise AlbumStoreError("MediaStore scan timeout")

        write_state("SAVING_CAPTION_NOTE", job_id, album=album, device_path=dst, media_store_verified=True)
        note = save_caption_note(job, manifest, run_dir)

        result = {
            "status": "STORED_IN_ALBUM",
            "job_id": job_id,
            "album": album,
            "device_path": dst,
            "media_store_verified": True,
            "note_saved": True,
            "note_app": note["note_app"],
            "note_method": note["note_method"],
            "caption_sha256": note["caption_sha256"],
            "stored_at": now_iso(),
            "initial_power_state": initial,
        }
        write_json_atomic(run_dir / "result.json", result)
        write_state(
            "STORED_IN_ALBUM",
            job_id,
            album=album,
            device_path=dst,
            media_store_verified=True,
            note_saved=True,
            note_app=note["note_app"],
        )
        return result
    except Exception as exc:
        error = str(exc)
        write_state("ALBUM_STORE_FAILED", job_id, album=album, reason=error)
        raise
    finally:
        try:
            power = restore_power_state(initial)
            write_json_atomic(run_dir / "power-restore.json", power)
        except Exception as restore_exc:
            write_json_atomic(run_dir / "power-restore.json", {
                "status": "POWER_RESTORE_FAILED",
                "initial_power_state": initial,
                "reason": str(restore_exc),
                "timestamp": now_iso(),
            })
            if result is not None and error is None:
                # Storage truth remains successful; power restore is observational.
                pass
        finally:
            claim_cm.__exit__(None, None, None)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("job_id")
    ap.add_argument("--album", default=DEFAULT_ALBUM)
    args = ap.parse_args()
    try:
        result = store(args.job_id, args.album)
    except Exception as exc:
        print(json.dumps({"status": "ALBUM_STORE_FAILED", "job_id": args.job_id, "reason": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
