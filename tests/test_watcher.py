"""Behavior tests for core.watcher (ManualSource + fake deliver only)."""
import unittest

from core.delivery import ACCEPTED
from core.source import ManualSource
from core.watcher import Watcher

MSG = "[MSG]\nhello\n[/MSG]"


class WatcherTest(unittest.TestCase):
    def test_first_poll(self):
        src = ManualSource()
        src.upsert("m1", MSG, final=True)
        watcher = Watcher(src, lambda t: (ACCEPTED, "x"))
        results = watcher.poll()
        self.assertEqual(results, [{"id": "m1", "version": 1,
                                    "disposition": "accepted"}])
        self.assertIsNotNone(watcher.token())

    def test_no_new_items(self):
        src = ManualSource()
        watcher = Watcher(src, lambda t: (ACCEPTED, "x"))
        self.assertEqual(watcher.poll(), [])
        self.assertEqual(watcher.poll(), [])

    def test_new_final_item(self):
        src = ManualSource()
        watcher = Watcher(src, lambda t: (ACCEPTED, "x"))
        watcher.poll()
        src.upsert("m2", MSG, final=True)
        results = watcher.poll()
        self.assertEqual([(r["id"], r["disposition"]) for r in results],
                         [("m2", "accepted")])

    def test_partial_item(self):
        src = ManualSource()
        src.upsert("m1", "half written")
        watcher = Watcher(src, lambda t: (ACCEPTED, "x"))
        results = watcher.poll()
        self.assertEqual(results, [{"id": "m1", "version": 1,
                                    "disposition": "skipped"}])

    def test_multiple_items(self):
        src = ManualSource()
        src.upsert("a", MSG, final=True)
        src.upsert("b", "partial")
        src.upsert("c", "note", final=True)
        watcher = Watcher(src, lambda t: (ACCEPTED, "x"))
        results = watcher.poll()
        self.assertEqual([(r["id"], r["disposition"]) for r in results],
                         [("a", "accepted"), ("b", "skipped"),
                          ("c", "no-message")])

    def test_second_poll_does_not_duplicate(self):
        delivered = []

        def deliver(text):
            delivered.append(text)
            return ACCEPTED, "x"

        src = ManualSource()
        src.upsert("m1", MSG, final=True)
        watcher = Watcher(src, deliver)
        watcher.poll()
        self.assertEqual(watcher.poll(), [])
        self.assertEqual(delivered, ["hello"])

    def test_failure_does_not_advance_token(self):
        src = ManualSource()
        src.upsert("m1", MSG, final=True)

        def boom(text):
            raise RuntimeError("down")

        watcher = Watcher(src, boom)
        with self.assertRaises(RuntimeError):
            watcher.poll()
        self.assertIsNone(watcher.token())
        # recovered on the next poll with a working deliver
        delivered = []

        def deliver(text):
            delivered.append(text)
            return ACCEPTED, "x"

        watcher2 = Watcher(src, deliver)
        # NOTE: watcher2 is a new Watcher (token None): replays from start.
        results = watcher2.poll()
        self.assertEqual(results[0]["disposition"], "accepted")
        self.assertEqual(delivered, ["hello"])

    def test_new_item_after_failure_recovered(self):
        src = ManualSource()
        src.upsert("m1", MSG, final=True)
        calls = {"fail": True}

        def flaky(text):
            if calls["fail"]:
                raise RuntimeError("transient")
            return ACCEPTED, "x"

        watcher = Watcher(src, flaky)
        with self.assertRaises(RuntimeError):
            watcher.poll()
        calls["fail"] = False
        src.upsert("m2", MSG, final=True)
        results = watcher.poll()  # SAME watcher: m1 retried, m2 new
        self.assertEqual([(r["id"], r["disposition"]) for r in results],
                         [("m1", "accepted"), ("m2", "accepted")])

    def test_works_without_knowing_session_source(self):
        import core.watcher as mod
        source = open(mod.__file__, encoding="utf-8").read()
        self.assertNotIn("SessionSource", source)
        self.assertNotIn("sqlite", source)
        src = ManualSource()
        src.upsert("m1", MSG, final=True)
        results = Watcher(src, lambda t: (ACCEPTED, "x")).poll()
        self.assertEqual(results[0]["disposition"], "accepted")

    def test_versions_follow_source_contract(self):
        src = ManualSource()
        src.upsert("m1", "v1")
        watcher = Watcher(src, lambda t: (ACCEPTED, "x"))
        first = watcher.poll()
        self.assertEqual(first[0]["version"], 1)
        src.upsert("m1", MSG, final=True)
        second = watcher.poll()
        self.assertEqual(second, [{"id": "m1", "version": 2,
                                   "disposition": "accepted"}])


if __name__ == "__main__":
    unittest.main()
