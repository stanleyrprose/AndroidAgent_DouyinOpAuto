"""Sprint 1 semantic graph regression candidates; not executed in development."""
import unittest
from automation import state_integrity as si


class SemanticGraphIntegrityTests(unittest.TestCase):
    def node(self, identity, parent=None, **kwargs):
        return {"node_id": identity, "parent_id": parent, "enabled": True, **kwargs}

    def test_exact_text_and_description(self):
        obs = {"elements": [self.node("a", text="Publish", content_desc="Confirm"),
                            self.node("b", text="Cancel", content_desc="Dismiss")]}
        self.assertEqual([n["node_id"] for n in si.match_elements(
            obs, {"text": "Publish", "content_desc": "Confirm"})], ["a"])

    def test_duplicate_missing_or_orphan_node_fails_closed(self):
        candidates = ([self.node("a"), self.node("a")],
                      [self.node("a"), {"parent_id": "a"}],
                      [self.node("a", "missing")])
        for rows in candidates:
            with self.subTest(rows=rows):
                with self.assertRaises(si.StateIntegrityError):
                    si.match_elements({"elements": rows}, {"enabled": True})

    def test_cycle_fails_closed(self):
        for rows in ([self.node("a", "a")],
                     [self.node("a", "b"), self.node("b", "a")]):
            with self.subTest(rows=rows):
                with self.assertRaises(si.StateIntegrityError):
                    si.match_elements({"elements": rows}, {"has_ancestor": {"enabled": True}})

    def test_valid_ancestor_and_descendant(self):
        obs = {"elements": [self.node("root", text="Parent"),
                            self.node("child", "root", text="Child"),
                            self.node("leaf", "child", text="Leaf")]}
        self.assertEqual([n["node_id"] for n in si.match_elements(
            obs, {"text": "Leaf", "has_ancestor": {"text": "Parent"}})], ["leaf"])
        self.assertEqual([n["node_id"] for n in si.match_elements(
            obs, {"text": "Parent", "has_descendant": {"text": "Leaf"}})], ["root"])

class NestedSelectorParityTests(unittest.TestCase):
    def setUp(self):
        self.obs = {"elements": [
            {"node_id": "root", "parent_id": None, "text": "Root", "enabled": True},
            {"node_id": "child", "parent_id": "root", "text": "Child", "enabled": True},
            {"node_id": "leaf", "parent_id": "child", "text": "Leaf", "enabled": True},
        ]}

    def test_direct_child_differs_from_descendant(self):
        self.assertEqual(si.match_elements(self.obs, {
            "text": "Root", "has_child": {"text": "Leaf"}}), [])
        self.assertEqual(len(si.match_elements(self.obs, {
            "text": "Root", "has_descendant": {"text": "Leaf"}})), 1)

    def test_nested_relations(self):
        result = si.match_elements(self.obs, {
            "text": "Root", "has_child": {
                "text": "Child", "has_child": {"text": "Leaf"}}})
        self.assertEqual([row["node_id"] for row in result], ["root"])

    def test_unknown_or_malformed_selectors_fail_closed(self):
        for selector in ({"unknown_key": "ignored"},
                         {"has_child": "invalid"},
                         {"enabled": "true"},
                         {"has_child": {}},
                         {"text": None}):
            with self.subTest(selector=selector):
                with self.assertRaises(si.StateIntegrityError):
                    si.match_elements(self.obs, selector)

    def test_fingerprint_selector_projection_preserves_child(self):
        selector = {"text": "Root", "has_child": {"text": "Child"}}
        self.assertEqual(si._selector_projection(selector), selector)
