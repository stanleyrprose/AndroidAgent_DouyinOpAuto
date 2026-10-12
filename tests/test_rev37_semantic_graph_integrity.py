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
