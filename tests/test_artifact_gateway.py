import importlib.util
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

PULLER = load_module(ROOT / "scripts" / "pull-artifact-bundle.py", "artifact_puller")
EXPORTER = load_module(ROOT / "mac" / "media-export" / "export_job.py", "artifact_exporter")

class ArtifactGatewayTest(unittest.TestCase):
    def test_safe_names(self):
        self.assertTrue(PULLER.safe_name("app.apk"))
        self.assertFalse(PULLER.safe_name("../app.apk"))
        self.assertFalse(PULLER.safe_name("a/b.apk"))
        self.assertFalse(PULLER.safe_name(".."))

    def test_validate_manifest(self):
        manifest = {
            "schema_version": 1,
            "job_id": "deploy-1",
            "artifacts": [{
                "name": "app.apk",
                "size": 3,
                "sha256": "a" * 64,
                "url": "https://example.invalid/cap/redacted/deploy-1/app.apk",
            }],
        }
        job_id, artifacts = PULLER.validate_manifest(manifest)
        self.assertEqual(job_id, "deploy-1")
        self.assertEqual(artifacts[0]["name"], "app.apk")

    def test_reject_bad_manifest(self):
        manifest = {
            "schema_version": 1,
            "job_id": "deploy-1",
            "artifacts": [{
                "name": "app.apk",
                "size": 3,
                "sha256": "not-a-hash",
                "url": "http://example.invalid/app.apk",
            }],
        }
        with self.assertRaises(ValueError):
            PULLER.validate_manifest(manifest)

    def test_sha256_helpers_agree(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "x.bin"
            path.write_bytes(b"artifact")
            self.assertEqual(PULLER.sha256_file(path), EXPORTER.sha256(path))

if __name__ == "__main__":
    unittest.main()
