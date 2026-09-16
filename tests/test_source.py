"""Behavior tests for core.source (contract only, no clock, no I/O)."""
import unittest

from core.source import ManualSource, Source


class SourceTest(unittest.TestCase):
    def test_empty_source(self):
        src = ManualSource()
        items, token = src.changes(None)
        self.assertEqual((items, token), ([], 0))

    def test_first_item(self):
        src = ManualSource()
        src.upsert("m1", "hello")
        items, token = src.changes(None)
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["id"], "m1")
        self.assertEqual(item["version"], 1)
        self.assertFalse(item["final"])
        self.assertEqual(item["text"], "hello")
        self.assertNotIn("seq", item)

    def test_multiple_versions_monotonic(self):
        src = ManualSource()
        self.assertEqual(src.upsert("m1", "v1"), 1)
        self.assertEqual(src.upsert("m1", "v2"), 2)
        self.assertEqual(src.upsert("m1", "v3", final=True), 3)
        items, _ = src.changes(None)
        self.assertEqual(len(items), 1)  # latest state only
        self.assertEqual(items[0]["version"], 3)
        self.assertTrue(items[0]["final"])

    def test_partial_item_message_evolves_to_final(self):
        # scan 1: v1 final=False; scan 2: v2 final=False; scan 3: v3 final=True
        src = ManualSource()
        src.upsert("m1", "part one")
        items1, t1 = src.changes(None)
        self.assertFalse(items1[0]["final"])
        src.upsert("m1", "part one two")
        items2, t2 = src.changes(t1)
        self.assertEqual(len(items2), 1)  # still eligible, never lost
        self.assertFalse(items2[0]["final"])
        src.upsert("m1", "part one two done", final=True)
        items3, t3 = src.changes(t2)
        self.assertTrue(items3[0]["final"])
        self.assertGreater(t3, t2)
        self.assertGreater(t2, t1)

    def test_token_advances(self):
        src = ManualSource()
        src.upsert("a", "x")
        _, t1 = src.changes(None)
        src.upsert("b", "y")
        items, t2 = src.changes(t1)
        self.assertEqual([i["id"] for i in items], ["b"])
        self.assertGreater(t2, t1)
        items3, t3 = src.changes(t2)
        self.assertEqual(items3, [])
        self.assertEqual(t3, t2)

    def test_non_final_stays_eligible(self):
        src = ManualSource()
        src.upsert("m1", "partial")
        items1, t1 = src.changes(None)
        # consumer does NOT adopt the token: same item comes back
        items_again, _ = src.changes(None)
        self.assertEqual(items_again, items1)
        _ = t1

    def test_invalid_token_rejected(self):
        src = ManualSource()
        for bad in ("x", -1, 1.5, True, [0]):
            with self.assertRaises(ValueError):
                src.changes(bad)
        # valid tokens keep working afterwards
        items, _ = src.changes(None)
        self.assertEqual(items, [])

    def test_monotonic_versions_across_ids(self):
        src = ManualSource()
        src.upsert("a", "1")
        src.upsert("b", "1")
        src.upsert("a", "2")
        items, _ = src.changes(None)
        by_id = {i["id"]: i["version"] for i in items}
        self.assertEqual(by_id, {"a": 2, "b": 1})
        # ordered by sequence: b (older) before a (newer)
        self.assertEqual([i["id"] for i in items], ["b", "a"])

    def test_no_clock_no_io(self):
        import core.source as mod
        source = open(mod.__file__, encoding="utf-8").read()
        for forbidden in ("time.", "sleep", "thread", "socket", "open(",
                          "sqlite", "subprocess"):
            self.assertNotIn(forbidden, source)

    def test_satisfies_protocol(self):
        self.assertIsInstance(ManualSource(), Source)


if __name__ == "__main__":
    unittest.main()
