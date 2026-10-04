from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

from pipeline.telegram_notify import render_message, send_status


class TelegramNotifyTests(unittest.TestCase):
    def test_render_terminal_success(self):
        msg = render_message("PUBLISHED_VERIFIED", "dy-123", "profile exact-caption matched")
        self.assertIn("已发布（已验证）", msg)
        self.assertIn("dy-123", msg)
        self.assertIn("profile exact-caption matched", msg)

    def test_render_reconcile_warns_without_retry_language(self):
        msg = render_message("RECONCILE_REQUIRED", "dy-456")
        self.assertIn("禁止重复发布", msg)

    @patch("pipeline.telegram_notify._resolve_sender", return_value=None)
    def test_missing_sender_is_best_effort(self, _sender):
        receipt = send_status("RECEIVED", "dy-1")
        self.assertFalse(receipt["sent"])
        self.assertEqual(receipt["reason"], "HERMES_WRAPPER_NOT_FOUND")

    @patch("pipeline.telegram_notify._resolve_sender", return_value="/tmp/y700automation")
    @patch("pipeline.telegram_notify.subprocess.run")
    def test_send_does_not_echo_transport_output(self, run_mock, _sender):
        run_mock.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout='{"chat_id":"private"}', stderr=""
        )
        receipt = send_status("DRY_RUN_PASS", "dy-2", detail="PUBLIC observed")
        self.assertTrue(receipt["sent"])
        self.assertNotIn("chat_id", receipt)
        cmd = run_mock.call_args.args[0]
        self.assertEqual(cmd[0], "/tmp/y700automation")
        self.assertIn("telegram", cmd)
        self.assertIn("PUBLIC observed", cmd[-1])


if __name__ == "__main__":
    unittest.main()
