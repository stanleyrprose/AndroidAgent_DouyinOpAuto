import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.common import atomic_json
from pipeline.telegram_media import deliver, MediaDeliveryError


class TelegramMediaTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.job = Path(temp.name) / 'job'
        (self.job / 'production').mkdir(parents=True)
        (self.job / 'source').mkdir()
        self.video = self.job / 'production/video.my.mp4'
        self.video.write_bytes(b'exact mp4 fixture')
        atomic_json(self.job / 'state.json', {'workflow_intent': 'STORE_ALBUM'})
        self.env = patch.dict(os.environ, {'Y700_TG_CHAT_ID': '-123', 'Y700_TG_MEDIA_SENDER': '/fake/media'}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.success = {'ok': True, 'result': {'message_id': 7, 'chat': {'id': -123}}}

    def receipt(self):
        return json.loads((self.job / 'export/telegram-media-receipt.json').read_text())

    def test_same_bytes_and_idempotent_resume(self):
        before = self.video.read_bytes()
        with patch('pipeline.telegram_media._send', return_value=self.success) as send:
            first = deliver(self.job)
            self.assertEqual(deliver(self.job), first)
            self.assertEqual(send.call_args.args[0].resolve(), self.video.resolve())
            self.assertEqual(send.call_args.args[1], '-123')
        self.assertEqual(self.video.read_bytes(), before)
        self.assertEqual(first['status'], 'SENT')

    def test_all_intents_select_correct_mp4(self):
        for intent in ('DIRECT_DOWNLOAD', 'STORE_ALBUM', 'AUTO_PUBLISH'):
            with self.subTest(intent=intent):
                record = self.job / 'export/telegram-media-receipt.json'
                record.unlink(missing_ok=True)
                atomic_json(self.job / 'state.json', {'workflow_intent': intent})
                original = self.job / 'source/original.mp4'
                original.write_bytes(b'original')
                atomic_json(self.job / 'source/source.json', {'video_path': str(original)})
                with patch('pipeline.telegram_media._send', return_value=self.success) as send:
                    deliver(self.job)
                    self.assertEqual(send.call_args.args[0].resolve(), (original if intent == 'DIRECT_DOWNLOAD' else self.video).resolve())

    def test_sha_or_destination_change_blocks(self):
        with patch('pipeline.telegram_media._send', return_value=self.success) as send:
            deliver(self.job)
            self.video.write_bytes(b'changed')
            with self.assertRaisesRegex(MediaDeliveryError, 'IDENTITY'):
                deliver(self.job)
            self.assertEqual(send.call_count, 1)

    def test_size_does_not_send(self):
        with patch.dict(os.environ, {'Y700_TG_MEDIA_MAX_BYTES': '1'}), patch('pipeline.telegram_media._send') as send:
            with self.assertRaisesRegex(MediaDeliveryError, 'SIZE'):
                deliver(self.job)
            send.assert_not_called()
        self.assertTrue(self.video.exists())

    def test_ambiguous_delivery_never_replays(self):
        with patch('pipeline.telegram_media._send', side_effect=MediaDeliveryError('DELIVERY_UNCERTAIN')) as send:
            for _ in range(2):
                with self.assertRaisesRegex(MediaDeliveryError, 'UNCERTAIN'):
                    deliver(self.job)
            self.assertEqual(send.call_count, 1)
        self.assertEqual(self.receipt()['status'], 'UNCERTAIN')

    def test_definite_rejection_bounded_retry_and_resume(self):
        rejected = {'ok': False, 'error_code': 429, 'parameters': {'retry_after': 0}}
        with patch('pipeline.telegram_media._send', return_value=rejected) as send:
            with self.assertRaisesRegex(MediaDeliveryError, 'REJECTED'):
                deliver(self.job)
            self.assertEqual(send.call_count, 3)
        with patch('pipeline.telegram_media._send', return_value=self.success):
            self.assertEqual(deliver(self.job)['status'], 'SENT')

    def test_wrong_chat_blocks(self):
        with patch('pipeline.telegram_media._send', return_value={'ok': True, 'result': {'message_id': 1, 'chat': {'id': 2}}}):
            with self.assertRaises(MediaDeliveryError):
                deliver(self.job)
        self.assertEqual(self.receipt()['status'], 'UNCERTAIN')

    def test_pull_gate_failure_never_contacts_y700(self):
        from pipeline.media_lifecycle import pull_verify_clean, TransferSafetyError
        with patch('pipeline.telegram_media.deliver', side_effect=MediaDeliveryError('blocked')), patch('pipeline.media_lifecycle.subprocess.run') as remote:
            with self.assertRaises(TransferSafetyError):
                pull_verify_clean(self.job, ssh_target='y700', manifest_url='https://example.test/manifest')
            remote.assert_not_called()

    def test_crash_journal_blocks_resume(self):
        with patch('pipeline.telegram_media._send', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                deliver(self.job)
        with patch('pipeline.telegram_media._send') as send:
            with self.assertRaisesRegex(MediaDeliveryError, 'UNCERTAIN'):
                deliver(self.job)
            send.assert_not_called()
