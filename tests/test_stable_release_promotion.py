import os
import pathlib
import subprocess
import tempfile
import unittest


SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "promote-stable-release.sh"


class StableReleasePromotionTest(unittest.TestCase):
    def run_cmd(self, *args, cwd=None, check=True, env=None):
        return subprocess.run(
            args,
            cwd=cwd,
            check=check,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )

    def make_release(self, root: pathlib.Path, name: str) -> pathlib.Path:
        release = root / name
        release.mkdir()
        self.run_cmd("git", "init", "-q", cwd=release)
        self.run_cmd("git", "config", "user.email", "test@example.com", cwd=release)
        self.run_cmd("git", "config", "user.name", "Test", cwd=release)
        (release / "marker.txt").write_text(name + "\n")
        self.run_cmd("git", "add", ".", cwd=release)
        self.run_cmd("git", "commit", "-qm", name, cwd=release)
        return release

    def test_promotion_uses_relative_symlink_and_records_previous_release(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td) / "workspaces"
            root.mkdir()
            self.make_release(root, "y700-agent-release-old")
            self.make_release(root, "y700-agent-release-new")

            stable = root / "y700-agent"
            stable.symlink_to("y700-agent-release-old")
            rollback = pathlib.Path(td) / "deploy-previous-release"

            env = os.environ.copy()
            env["Y700_WORKSPACES_ROOT"] = str(root)
            env["Y700_STABLE_LINK"] = str(stable)
            env["Y700_ROLLBACK_FILE"] = str(rollback)

            out = self.run_cmd(
                str(SCRIPT),
                "y700-agent-release-new",
                env=env,
            )
            self.assertIn("PROMOTED", out.stdout)
            self.assertEqual(os.readlink(stable), "y700-agent-release-new")
            self.assertFalse(os.path.isabs(os.readlink(stable)))
            self.assertEqual(
                rollback.read_text().strip(),
                "y700-agent-release-old",
            )

    def test_rejects_non_basename_release(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td) / "workspaces"
            root.mkdir()
            env = os.environ.copy()
            env["Y700_WORKSPACES_ROOT"] = str(root)
            env["Y700_STABLE_LINK"] = str(root / "y700-agent")
            env["Y700_ROLLBACK_FILE"] = str(pathlib.Path(td) / "rollback")
            out = self.run_cmd(
                str(SCRIPT),
                "/tmp/y700-agent-release-bad",
                check=False,
                env=env,
            )
            self.assertEqual(out.returncode, 65)
            self.assertIn("INVALID_RELEASE_BASENAME", out.stderr)


if __name__ == "__main__":
    unittest.main()
