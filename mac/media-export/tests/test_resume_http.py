import hashlib
import json
import secrets
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import Handler


class ResumeHTTPTests(unittest.TestCase):
    def test_range_etag_and_changed_resource(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            job = root / "test-job"
            job.mkdir()
            token = secrets.token_hex(12)
            (job / ".capability").write_text(json.dumps({"token": token, "expires_at": int(time.time()) + 120}))
            content = b"test-media" * 1000
            (job / "video.mp4").write_bytes(content)
            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            server.root = root
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            url = f"http://127.0.0.1:{server.server_port}/cap/{token}/test-job/video.mp4"
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={"Range": "bytes=100-199"})) as response:
                    self.assertEqual(response.status, 206)
                    self.assertEqual(response.read(), content[100:200])
                    self.assertEqual(response.headers["ETag"], '"' + hashlib.sha256(content).hexdigest() + '"')
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(urllib.request.Request(url, headers={"Range": "bytes=100-199", "If-Range": '"stale"'}))
                self.assertEqual(error.exception.code, 412)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
