from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "publisher" / "store_direct_download.py"
COMPLETE = ROOT / "mac" / "production-pipeline" / "scripts" / "complete-direct-download.sh"
ENTRY = ROOT / "mac" / "production-pipeline" / "scripts" / "direct-download-to-y700.sh"
SOUL = ROOT / "config" / "hermes-y700automation-SOUL.md"


class DirectDownloadContractTests(unittest.TestCase):
    def test_control_contract_is_video_only(self) -> None:
        soul = SOUL.read_text(encoding="utf-8")
        self.assertIn("直接下载<sep><Douyin share text or URL>", soul)
        self.assertIn("Direct Download<sep><Douyin share text or URL>", soul)
        self.assertIn("DIRECT_DOWNLOAD", soul)
        self.assertIn("direct-download-to-y700.sh", soul)

        entry = ENTRY.read_text(encoding="utf-8")
        complete = COMPLETE.read_text(encoding="utf-8")
        store = STORE.read_text(encoding="utf-8")
        joined = "\n".join([entry, complete, store])
        self.assertIn("pull-artifact-bundle.py", complete)
        self.assertIn("original.mp4", joined)
        self.assertIn("DIRECT_DOWNLOADED", joined)
        self.assertNotIn("approve-public-commit.sh", joined)
        self.assertNotIn("publish-async.sh", joined)
        self.assertNotIn("com.zui.notes", joined)
        self.assertNotIn("caption.my.txt", joined)
        self.assertNotIn("apps.tiktok", joined)

    def test_y700_direct_store_verifies_media_without_screen_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            job_id = "dd-1234567890123456789"
            pull = td / "pull"
            bundle = pull / job_id
            bundle.mkdir(parents=True)
            (bundle / ".complete").write_text("verified\n", encoding="utf-8")
            original = b"sample-video-bytes"
            host_media = td / "host-media"
            mock_source = td / "mock-original.mp4"
            mock_source.write_bytes(original)
            (bundle / "manifest.json").write_text(json.dumps({
                "schema_version": 1,
                "job_id": job_id,
                "kind": "generic-artifact",
                "expires_at": 9999999999,
                "artifacts": [{
                    "name": "original.mp4",
                    "size": len(original),
                    "sha256": hashlib.sha256(original).hexdigest(),
                    "url": "https://example.invalid/cap/redacted/original.mp4",
                }],
            }), encoding="utf-8")

            run_root = td / "runs"
            state = td / "state.json"
            root_log = td / "root.log"
            root_exec = td / "root-exec.sh"
            root_exec.write_text(
                f'''#!/bin/bash
printf '%s\\n' "$*" >> "{root_log}"
case "$*" in
  *"cp "*"original.mp4"*)
    mkdir -p "{host_media}/Movies/Y700Agent"
    cp "{mock_source}" "{host_media}/Movies/Y700Agent/{job_id}.mp4"
    ;;
  *"content query"*) echo "Row: 0 _id=1, _display_name={job_id}.mp4, relative_path=Movies/Y700Agent/" ;;
esac
''',
                encoding="utf-8",
            )
            root_exec.chmod(0o755)

            androidctl = td / "androidctl.sh"
            screen_used = td / "screen-used.txt"
            androidctl.write_text(
                '#!/bin/bash\n' + f'touch "{screen_used}"\n' + 'exit 87\n',
                encoding="utf-8",
            )
            androidctl.chmod(0o755)

            unlock = td / "secure-unlock.sh"
            # Direct download must succeed without needing a screen unlock.
            unlock.write_text('#!/bin/bash\nexit 91\n', encoding="utf-8")
            unlock.chmod(0o755)

            env = os.environ.copy()
            env.update({
                "Y700_DIRECT_PULL_ROOT": str(pull),
                "Y700_DIRECT_HOST_PULL_ROOT": "/fake/host/direct-download",
                "Y700_DIRECT_HOST_MEDIA_ROOT": str(host_media),
                "Y700_DIRECT_RUN_ROOT": str(run_root),
                "Y700_DIRECT_STATE": str(state),
                "Y700_ROOT_EXEC": str(root_exec),
                "Y700_ANDROIDCTL": str(androidctl),
                "Y700_SECURE_UNLOCK": str(unlock),
            })
            p = subprocess.run(
                ["python3", str(STORE), job_id],
                env=env,
                text=True,
                capture_output=True,
            )
            self.assertEqual(p.returncode, 0, p.stderr)
            out = json.loads(p.stdout.strip().splitlines()[-1])
            self.assertEqual(out["status"], "DIRECT_DOWNLOADED")
            self.assertTrue(out["media_store_verified"])
            self.assertFalse(out["note_saved"])
            self.assertEqual(out["device_path"], f"/sdcard/Movies/Y700Agent/{job_id}.mp4")

            commands = root_log.read_text(encoding="utf-8")
            self.assertIn("original.mp4", commands)
            self.assertIn("Movies/Y700Agent", commands)
            self.assertIn("set -e", commands)
            self.assertNotIn("KEYCODE_SLEEP", commands)
            self.assertFalse(screen_used.exists())
            self.assertTrue((run_root / job_id / "file-verification.json").is_file())
            self.assertNotIn("com.zui.notes", commands)
            self.assertNotIn("tiktok", commands.lower())
            power = json.loads((run_root / job_id / "power-restore.json").read_text(encoding="utf-8"))
            self.assertEqual(power["status"], "NO_SCREEN_MUTATION")


    def test_direct_store_rejects_corrupted_copy_even_with_mediastore_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            job_id = "dd-1234567890123456789"
            bundle = td / "pull" / job_id
            bundle.mkdir(parents=True)
            (bundle / ".complete").write_text("verified\\n", encoding="utf-8")
            expected = b"the-correct-source"
            (bundle / "manifest.json").write_text(json.dumps({
                "schema_version": 1, "kind": "generic-artifact", "job_id": job_id,
                "artifacts": [{"name": "original.mp4", "size": len(expected),
                               "sha256": hashlib.sha256(expected).hexdigest()}],
            }), encoding="utf-8")
            host_media = td / "android" / "Movies" / "Y700Agent"
            root = td / "root.sh"
            root.write_text(
                "#!/bin/bash\\n"
                'case "$*" in\\n'
                '  *"cp "*"original.mp4"*)\\n'
                f'    mkdir -p "{host_media}"\\n'
                f'    printf wrong-bytes > "{host_media}/{job_id}.mp4"\\n'
                '    ;;\\n'
                '  *"content query"*) echo "Row: 0 _id=1, _display_name='
                + job_id + '.mp4, relative_path=Movies/Y700Agent/" ;;\\n'
                'esac\\n', encoding="utf-8",
            )
            root.chmod(0o755)
            env = {**os.environ,
                   "Y700_DIRECT_PULL_ROOT": str(td / "pull"),
                   "Y700_DIRECT_HOST_MEDIA_ROOT": str(td / "android"),
                   "Y700_DIRECT_RUN_ROOT": str(td / "runs"),
                   "Y700_DIRECT_STATE": str(td / "state.json"),
                   "Y700_ROOT_EXEC": str(root)}
            proc = subprocess.run(["python3", str(STORE), job_id],
                                  env=env, capture_output=True, text=True)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("DIRECT_DOWNLOAD_FAILED", proc.stdout)
            self.assertFalse((td / "runs" / job_id / "result.json").exists())
            failure = json.loads((td / "runs" / job_id / "last-error.json").read_text())
            self.assertEqual(failure["stage"], "COPY_OR_VERIFY_FILE")

    def test_direct_store_rejects_invalid_manifest_digest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            job_id = "dd-12345"
            bundle = td / "pull" / job_id
            bundle.mkdir(parents=True)
            (bundle / ".complete").write_text("verified\\n", encoding="utf-8")
            (bundle / "manifest.json").write_text(json.dumps({
                "schema_version": 1, "kind": "generic-artifact", "job_id": job_id,
                "artifacts": [{"name": "original.mp4", "size": 12,
                               "sha256": "not-a-sha256"}],
            }), encoding="utf-8")
            env = {**os.environ, "Y700_DIRECT_PULL_ROOT": str(td / "pull")}
            proc = subprocess.run(["python3", str(STORE), job_id],
                                  env=env, capture_output=True, text=True)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("invalid original.mp4 SHA-256", proc.stdout)

    def test_direct_store_rejects_non_original_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            job_id = "dd-12345"
            bundle = td / "pull" / job_id
            bundle.mkdir(parents=True)
            (bundle / ".complete").write_text("verified\n", encoding="utf-8")
            (bundle / "manifest.json").write_text(json.dumps({
                "schema_version": 1,
                "job_id": job_id,
                "kind": "generic-artifact",
                "artifacts": [{
                    "name": "rendered.mp4",
                    "size": 1,
                    "sha256": "b" * 64,
                    "url": "https://example.invalid/rendered.mp4",
                }],
            }), encoding="utf-8")
            env = os.environ.copy()
            env["Y700_DIRECT_PULL_ROOT"] = str(td / "pull")
            p = subprocess.run(["python3", str(STORE), job_id], env=env, text=True, capture_output=True)
            self.assertNotEqual(p.returncode, 0)
            self.assertIn("DIRECT_DOWNLOAD_FAILED", p.stdout)

    def test_direct_store_reconciles_existing_verified_file_without_copy_or_unlock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            job_id = "dd-1234567890123456789"
            original = b"already-present-original-mp4"
            digest = __import__("hashlib").sha256(original).hexdigest()
            bundle = td / "pull" / job_id
            bundle.mkdir(parents=True)
            (bundle / ".complete").write_text("verified\n", encoding="utf-8")
            (bundle / "manifest.json").write_text(json.dumps({
                "schema_version": 1, "kind": "generic-artifact", "job_id": job_id,
                "artifacts": [{"name": "original.mp4", "size": len(original),
                               "sha256": digest, "url": "https://example.invalid/file"}],
            }), encoding="utf-8")
            album = td / "host-media" / "Movies" / "Y700Agent"
            album.mkdir(parents=True)
            (album / f"{job_id}.mp4").write_bytes(original)
            commands = td / "commands"
            root = td / "root.sh"
            root.write_text(
                '#!/bin/bash\nprintf "%s\\n" "$*" >> "' + str(commands) + '"\n'
                'case "$*" in *"content query"*) '
                'echo "Row: 0 _id=1, _display_name=' + job_id
                + '.mp4, relative_path=Movies/Y700Agent/" ;; esac\n',
                encoding="utf-8",
            )
            root.chmod(0o755)
            screen = td / "screen.sh"
            screen.write_text('#!/bin/bash\necho "mWakefulness=Asleep"\n', encoding="utf-8")
            screen.chmod(0o755)
            env = {**os.environ,
                   "Y700_DIRECT_PULL_ROOT": str(td / "pull"),
                   "Y700_DIRECT_HOST_MEDIA_ROOT": str(td / "host-media"),
                   "Y700_DIRECT_RUN_ROOT": str(td / "runs"),
                   "Y700_DIRECT_STATE": str(td / "state.json"),
                   "Y700_ROOT_EXEC": str(root),
                   "Y700_ANDROIDCTL": str(screen)}
            proc = subprocess.run(["python3", str(STORE), job_id],
                                  env=env, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            result = json.loads(proc.stdout)
            self.assertEqual(result["status"], "DIRECT_DOWNLOADED")
            self.assertTrue(result["reconciled_existing_file"])
            self.assertNotIn("cp ", commands.read_text())
            self.assertNotIn("KEYCODE_SLEEP", commands.read_text())

            # A repeated resume must use the success receipt without new actions.
            commands.unlink()
            proc = subprocess.run(["python3", str(STORE), job_id],
                                  env=env, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0)
            self.assertTrue(json.loads(proc.stdout)["idempotent"])
            self.assertFalse(commands.exists())

    def test_direct_store_rejects_different_existing_video_without_overwriting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            job_id = "dd-12345"
            bundle = td / "pull" / job_id
            bundle.mkdir(parents=True)
            (bundle / ".complete").write_text("verified\n", encoding="utf-8")
            (bundle / "manifest.json").write_text(json.dumps({
                "schema_version": 1, "kind": "generic-artifact", "job_id": job_id,
                "artifacts": [{"name": "original.mp4", "size": 5,
                               "sha256": "a" * 64, "url": "https://example.invalid/file"}],
            }), encoding="utf-8")
            album = td / "host-media" / "Movies" / "Y700Agent"
            album.mkdir(parents=True)
            existing = album / f"{job_id}.mp4"
            existing.write_bytes(b"wrong")
            env = {**os.environ,
                   "Y700_DIRECT_PULL_ROOT": str(td / "pull"),
                   "Y700_DIRECT_HOST_MEDIA_ROOT": str(td / "host-media")}
            proc = subprocess.run(["python3", str(STORE), job_id],
                                  env=env, capture_output=True, text=True)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("SHA-256 mismatch", proc.stdout)
            self.assertEqual(existing.read_bytes(), b"wrong")

    def test_mediastore_unavailable_preserves_file_proof_without_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            job_id = "dd-1234567890123456789"
            original = b"already-in-gallery"
            bundle = td / "pull" / job_id
            bundle.mkdir(parents=True)
            (bundle / ".complete").write_text("verified\\n", encoding="utf-8")
            (bundle / "manifest.json").write_text(json.dumps({
                "schema_version": 1, "kind": "generic-artifact", "job_id": job_id,
                "artifacts": [{"name": "original.mp4", "size": len(original),
                               "sha256": hashlib.sha256(original).hexdigest()}],
            }), encoding="utf-8")
            media = td / "media" / "Movies" / "Y700Agent"
            media.mkdir(parents=True)
            album_file = media / (job_id + ".mp4")
            album_file.write_bytes(original)
            root = td / "root.sh"
            root.write_text(
                '#!/bin/bash\\n'
                'case "$*" in *"content query"*) exit 42 ;; esac\\n',
                encoding="utf-8",
            )
            root.chmod(0o755)
            env = {**os.environ,
                   "Y700_DIRECT_PULL_ROOT": str(td / "pull"),
                   "Y700_DIRECT_HOST_MEDIA_ROOT": str(td / "media"),
                   "Y700_DIRECT_RUN_ROOT": str(td / "runs"),
                   "Y700_DIRECT_STATE": str(td / "state.json"),
                   "Y700_ROOT_EXEC": str(root)}
            proc = subprocess.run(["python3", str(STORE), job_id],
                                  env=env, capture_output=True, text=True)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("MediaStore query failed rc=42", proc.stdout)
            self.assertTrue((td / "runs" / job_id / "file-verification.json").is_file())
            self.assertFalse((td / "runs" / job_id / "result.json").exists())
            failure = json.loads((td / "runs" / job_id / "last-error.json").read_text())
            self.assertEqual(failure["stage"], "VERIFY_MEDIASTORE")
            self.assertEqual(failure["status"], "DIRECT_DOWNLOAD_HANDOFF_PENDING")
            self.assertEqual(album_file.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
