import unittest

from automation.vision_policy import (
    Route,
    SemanticStatus,
    VisionPolicy,
    decide_route,
)


TEMPLATE = {
    "content_desc": "Close",
    "fallback": [
        {
            "type": "vision_template",
            "template": "common/close.png",
            "confidence": 0.90,
        }
    ],
}


class VisionRoutingPolicyTest(unittest.TestCase):
    def test_semantic_success_never_invokes_vision(self):
        d = decide_route(
            semantic_status=SemanticStatus.RESOLVED,
            selector=TEMPLATE,
            policy=VisionPolicy(vision_enabled=True, mode="fallback", gate_v0_passed=True),
        )
        self.assertEqual(d.route, Route.SEMANTIC)
        self.assertTrue(d.action_authorized)

    def test_v0_benchmark_mode_never_authorizes_click(self):
        d = decide_route(
            semantic_status=SemanticStatus.NOT_FOUND,
            selector=TEMPLATE,
            policy=VisionPolicy(vision_enabled=True, mode="benchmark_only"),
        )
        self.assertEqual(d.route, Route.VISION_BENCHMARK_ONLY)
        self.assertFalse(d.action_authorized)

    def test_no_implicit_vision_when_selector_has_no_fallback(self):
        d = decide_route(
            semantic_status=SemanticStatus.NOT_FOUND,
            selector={"text": "Close"},
            policy=VisionPolicy(vision_enabled=True, mode="fallback", gate_v0_passed=True),
        )
        self.assertEqual(d.route, Route.UNRESOLVED)

    def test_template_fallback_requires_gate_v0(self):
        d = decide_route(
            semantic_status=SemanticStatus.NOT_FOUND,
            selector=TEMPLATE,
            policy=VisionPolicy(vision_enabled=True, mode="fallback", gate_v0_passed=False),
        )
        self.assertEqual(d.route, Route.BLOCKED)

    def test_template_precedes_ocr(self):
        selector = {
            "fallback": [
                {"type": "vision_template", "template": "x.png"},
                {"type": "vision_text", "pattern": "X"},
            ]
        }
        d = decide_route(
            semantic_status=SemanticStatus.AMBIGUOUS,
            selector=selector,
            policy=VisionPolicy(
                vision_enabled=True,
                mode="fallback",
                gate_v0_passed=True,
                template_enabled=True,
                ocr_enabled=True,
                gate_v2_passed=True,
            ),
        )
        self.assertEqual(d.route, Route.VISION_TEMPLATE)

    def test_ocr_requires_gate_v2(self):
        selector = {"fallback": [{"type": "vision_text", "pattern": "X"}]}
        d = decide_route(
            semantic_status=SemanticStatus.NOT_FOUND,
            selector=selector,
            policy=VisionPolicy(
                vision_enabled=True,
                mode="fallback",
                gate_v0_passed=True,
                ocr_enabled=True,
                gate_v2_passed=False,
            ),
        )
        self.assertEqual(d.route, Route.BLOCKED)

    def test_irreversible_vision_is_denied_by_default(self):
        d = decide_route(
            semantic_status=SemanticStatus.NOT_FOUND,
            selector=TEMPLATE,
            side_effect="EXTERNAL_IRREVERSIBLE",
            policy=VisionPolicy(
                vision_enabled=True,
                mode="fallback",
                gate_v0_passed=True,
            ),
            secondary_validation_available=True,
        )
        self.assertEqual(d.route, Route.BLOCKED)
        self.assertTrue(d.require_exact_input)
        self.assertTrue(d.require_secondary_validation)

    def test_irreversible_opt_in_still_requires_secondary_validation(self):
        d = decide_route(
            semantic_status=SemanticStatus.NOT_FOUND,
            selector=TEMPLATE,
            side_effect="EXTERNAL_IRREVERSIBLE",
            policy=VisionPolicy(
                vision_enabled=True,
                mode="fallback",
                gate_v0_passed=True,
                allow_high_risk_vision=True,
            ),
            secondary_validation_available=False,
        )
        self.assertEqual(d.route, Route.BLOCKED)

    def test_irreversible_opt_in_with_secondary_validation_can_route(self):
        d = decide_route(
            semantic_status=SemanticStatus.NOT_FOUND,
            selector=TEMPLATE,
            side_effect="EXTERNAL_IRREVERSIBLE",
            policy=VisionPolicy(
                vision_enabled=True,
                mode="fallback",
                gate_v0_passed=True,
                allow_high_risk_vision=True,
            ),
            secondary_validation_available=True,
        )
        self.assertEqual(d.route, Route.VISION_TEMPLATE)
        self.assertTrue(d.action_authorized)
        self.assertTrue(d.require_exact_input)


if __name__ == "__main__":
    unittest.main()
