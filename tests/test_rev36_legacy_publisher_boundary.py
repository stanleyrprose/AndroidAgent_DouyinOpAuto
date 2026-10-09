import unittest
from unittest.mock import patch

from publisher import controller


class Rev36LegacyPublisherBoundaryTests(unittest.TestCase):
    def test_androidctl_mutation_is_blocked_before_subprocess(self):
        with patch.object(controller, "run") as run:
            with self.assertRaisesRegex(controller.UIError, "LEGACY_MUTATOR_DISABLED"):
                controller.androidctl("tap", "100", "100")
        run.assert_not_called()

    def test_root_mutation_is_blocked_before_subprocess(self):
        with patch.object(controller, "run") as run:
            with self.assertRaisesRegex(controller.UIError, "LEGACY_MUTATOR_DISABLED"):
                controller.root_exec("input tap 100 100")
        run.assert_not_called()

    def test_observation_androidctl_remains_available(self):
        with patch.object(controller, "run") as run:
            controller.androidctl("activity", check=False)
        run.assert_called_once()

    def test_fast_state_root_dump_remains_observation_only(self):
        with patch.object(controller, "run") as run:
            controller.root_exec(
                "rm -f /tmp/x; toybox timeout 2 uiautomator dump /tmp/x >/dev/null 2>&1",
                check=False,
            )
        run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
