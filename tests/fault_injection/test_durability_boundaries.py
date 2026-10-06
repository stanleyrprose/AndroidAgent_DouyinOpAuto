from __future__ import annotations
import unittest
from tests.fault_injection.harness import FaultInjector, InjectedCrash, NAMED_BOUNDARIES

class FaultHarnessSelfTest(unittest.TestCase):
    def test_every_named_boundary_is_injectable(self):
        for point in NAMED_BOUNDARIES:
            with self.subTest(point=point):
                injector = FaultInjector(point)
                with self.assertRaisesRegex(InjectedCrash, point):
                    injector.hit(point)
                self.assertEqual(injector.seen, [point])

    def test_unknown_boundary_is_rejected(self):
        with self.assertRaises(ValueError):
            FaultInjector("unknown-boundary")

if __name__ == "__main__":
    unittest.main()
