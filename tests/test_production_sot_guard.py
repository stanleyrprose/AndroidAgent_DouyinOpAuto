import os
import pathlib
import subprocess
import tempfile
import unittest


SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "production-sot-status.sh"


class ProductionSotGuardTest(unittest.TestCase):
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

    def make_repo(self):
        td = tempfile.TemporaryDirectory()
        root = pathlib.Path(td.name)
        self.run_cmd("git", "init", "-q", cwd=root)
        self.run_cmd("git", "config", "user.email", "test@example.com", cwd=root)
        self.run_cmd("git", "config", "user.name", "Test", cwd=root)
        (root / "scripts").mkdir()
        (root / "docs").mkdir()
        (root / "automation").mkdir()
        (root / "scripts" / "x.sh").write_text("echo one\n")
        (root / "automation" / "core.py").write_text("VALUE = 1\n")
        (root / "docs" / "note.md").write_text("one\n")
        self.run_cmd("git", "add", ".", cwd=root)
        self.run_cmd("git", "commit", "-qm", "base", cwd=root)
        base = self.run_cmd("git", "rev-parse", "HEAD", cwd=root).stdout.strip()
        self.run_cmd("git", "branch", "main-ref", base, cwd=root)
        return td, root, base

    def guard(self, root, ref="main-ref"):
        env = os.environ.copy()
        env["Y700_STABLE_ROOT"] = str(root)
        env["Y700_MAIN_REF"] = ref
        return self.run_cmd(str(SCRIPT), check=False, env=env)

    def test_same_runtime_tree_is_healthy(self):
        td, root, _ = self.make_repo()
        with td:
            out = self.guard(root)
            self.assertEqual(out.returncode, 0)
            self.assertEqual(out.stdout.strip(), "HEALTHY")

    def test_docs_only_change_does_not_drift(self):
        td, root, _ = self.make_repo()
        with td:
            (root / "docs" / "note.md").write_text("two\n")
            self.run_cmd("git", "add", "docs/note.md", cwd=root)
            self.run_cmd("git", "commit", "-qm", "docs", cwd=root)
            self.run_cmd("git", "branch", "-f", "main-ref", "HEAD", cwd=root)
            self.run_cmd("git", "checkout", "-q", "HEAD~1", cwd=root)
            out = self.guard(root)
            self.assertEqual(out.returncode, 0)
            self.assertEqual(out.stdout.strip(), "HEALTHY")

    def test_runtime_change_is_drift(self):
        td, root, _ = self.make_repo()
        with td:
            (root / "automation" / "core.py").write_text("VALUE = 2\n")
            self.run_cmd("git", "add", "automation/core.py", cwd=root)
            self.run_cmd("git", "commit", "-qm", "runtime", cwd=root)
            self.run_cmd("git", "branch", "-f", "main-ref", "HEAD", cwd=root)
            self.run_cmd("git", "checkout", "-q", "HEAD~1", cwd=root)
            out = self.guard(root)
            self.assertEqual(out.returncode, 1)
            self.assertEqual(out.stdout.strip(), "DRIFT")

    def test_absolute_stable_symlink_is_drift(self):
        td, root, _ = self.make_repo()
        with td:
            stable = root.parent / "stable"
            stable.symlink_to(root.resolve())
            out = self.guard(stable)
            self.assertEqual(out.returncode, 1)
            self.assertEqual(out.stdout.strip(), "DRIFT")


if __name__ == "__main__":
    unittest.main()
