from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from publisher import publish_job


class PublishRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ready = Path(self.tmp.name) / "ready"
        self.published = Path(self.tmp.name) / "published"
        self.ready.mkdir()
        self.published.mkdir()
        (self.ready / "job-1").mkdir()

    def _common_patches(self, mode: str):
        manifest = {
            "job_id": "job-1",
            "publish_mode": mode,
            "caption_file": "caption.txt",
            "visibility": "PRIVATE",
        }
        return [
            mock.patch.object(publish_job, "READY", self.ready),
            mock.patch.object(publish_job, "PUBLISHED", self.published),
            mock.patch.object(publish_job, "load_manifest", return_value=manifest),
            mock.patch.object(publish_job, "load_metadata", return_value={}),
            mock.patch.object(publish_job, "read_text", return_value="caption"),
            mock.patch.object(publish_job, "find_published_duplicate", return_value=None),
            mock.patch.object(publish_job, "run"),
            mock.patch.object(publish_job, "update"),
        ]

    def test_dry_run_routes_only_to_generic_core(self) -> None:
        generic_result = {
            "engine": "androidx-uiautomator-2.4",
            "title": {"status": "SKIPPED"},
            "caption_verified": True,
            "visibility": "PRIVATE",
            "ui_state": {"state": "POST_CONFIG"},
            "workflow_job_id": "ui-1",
            "evidence": {"source_path": "/unused/in-test"},
        }
        patches = self._common_patches("DRY_RUN")
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            patches[5],
            patches[6],
            patches[7],
            mock.patch.object(
                publish_job.generic_tiktok,
                "prepare_dry_run",
                return_value=generic_result,
            ) as generic,
            mock.patch.object(publish_job.generic_tiktok, "force_stop") as force_stop,
            mock.patch.object(
                publish_job, "store_generic_evidence", return_value={"screenshot": "evidence/x.png"}
            ),
            mock.patch.object(publish_job.controller, "go_to_post_config") as legacy_nav,
            mock.patch.object(sys, "argv", ["publish_job.py", "job-1"]),
        ):
            publish_job.main()

        generic.assert_called_once_with(
            "caption",
            title="",
            visibility="PRIVATE",
            album="Y700Agent",
        )
        force_stop.assert_called_once()
        legacy_nav.assert_not_called()

    def test_commit_without_flag_never_starts_ui_navigation(self) -> None:
        patches = self._common_patches("COMMIT")
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            patches[5],
            patches[6],
            patches[7],
            mock.patch.object(publish_job.generic_tiktok, "commit_private") as generic_commit,
            mock.patch.object(publish_job.controller, "go_to_post_config") as legacy_nav,
            mock.patch.object(publish_job.controller, "restore_input_method"),
            mock.patch.object(sys, "argv", ["publish_job.py", "job-1"]),
        ):
            with self.assertRaisesRegex(publish_job.PublishError, "--commit"):
                publish_job.main()

        generic_commit.assert_not_called()
        legacy_nav.assert_not_called()

    def test_commit_routes_to_generic_core_and_never_legacy_publish(self) -> None:
        generic_result = {
            "engine": "androidx-uiautomator-2.4",
            "title": {"status": "SKIPPED"},
            "caption_verified": True,
            "visibility": "PRIVATE",
            "ui_state": {"state": "POST_CONFIG"},
            "workflow_job_id": "ui-ready",
            "commit_preflight_workflow_job_id": "ui-precommit",
            "commit_workflow_job_id": "ui-commit",
            "commit_dispatched": True,
            "evidence": {"source_path": "/unused/in-test"},
        }

        def fake_commit(*args, before_irreversible, **kwargs):
            before_irreversible()
            return generic_result

        patches = self._common_patches("COMMIT")
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            patches[5],
            patches[6],
            patches[7] as updates,
            mock.patch.object(
                publish_job.generic_tiktok,
                "commit_private",
                side_effect=fake_commit,
            ) as generic_commit,
            mock.patch.object(
                publish_job, "store_generic_evidence", return_value={"screenshot": "evidence/x.png"}
            ),
            mock.patch.object(
                publish_job,
                "verify_private_post",
                return_value={"verified": True, "method": "profile_private_exact_caption"},
            ),
            mock.patch.object(publish_job.controller, "go_to_post_config") as legacy_nav,
            mock.patch.object(publish_job.controller, "tap_publish") as legacy_publish,
            mock.patch.object(publish_job.controller, "restore_input_method"),
            mock.patch.object(sys, "argv", ["publish_job.py", "job-1", "--commit"]),
        ):
            publish_job.main()

        generic_commit.assert_called_once()
        legacy_nav.assert_not_called()
        legacy_publish.assert_not_called()
        statuses = [c.args[0] for c in updates.call_args_list]
        self.assertIn("COMMITTING", statuses)
        self.assertEqual(statuses[-1], "PUBLISHED")
        self.assertTrue((self.published / "job-1" / "publish-result.json").is_file())

    def test_post_click_verification_failure_is_ambiguous_not_failed(self) -> None:
        generic_result = {
            "engine": "androidx-uiautomator-2.4",
            "title": {"status": "SKIPPED"},
            "caption_verified": True,
            "visibility": "PRIVATE",
            "ui_state": {"state": "POST_CONFIG"},
            "workflow_job_id": "ui-ready",
            "commit_preflight_workflow_job_id": "ui-precommit",
            "commit_workflow_job_id": "ui-commit",
            "commit_dispatched": True,
            "evidence": {"source_path": "/unused/in-test"},
        }

        def fake_commit(*args, before_irreversible, **kwargs):
            before_irreversible()
            return generic_result

        patches = self._common_patches("COMMIT")
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            patches[5],
            patches[6],
            patches[7] as updates,
            mock.patch.object(
                publish_job.generic_tiktok,
                "commit_private",
                side_effect=fake_commit,
            ),
            mock.patch.object(
                publish_job, "store_generic_evidence", return_value={"screenshot": "evidence/x.png"}
            ),
            mock.patch.object(
                publish_job,
                "verify_private_post",
                side_effect=publish_job.PublishError("profile temporarily unavailable"),
            ),
            mock.patch.object(publish_job.controller, "restore_input_method"),
            mock.patch.object(sys, "argv", ["publish_job.py", "job-1", "--commit"]),
        ):
            with self.assertRaisesRegex(publish_job.PublishError, "profile temporarily unavailable"):
                publish_job.main()

        last = updates.call_args_list[-1]
        self.assertEqual(last.args[0], "AMBIGUOUS_COMMIT_NEEDS_RECONCILE")
        self.assertFalse(last.kwargs["retry_allowed"])
        self.assertNotEqual(last.args[0], "FAILED")


if __name__ == "__main__":
    unittest.main()
