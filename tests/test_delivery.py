"""Behavior tests for core.delivery: put/take/settle (no transport)."""
import unittest

from core.audit import MemoryAuditSink
from core.delivery import (
    ACCEPTED,
    DELIVERED,
    DROPPED,
    SUPERSEDED,
    OneShotDelivery,
)
from core.gate import ManualGate


def make(open_=True, **kwargs):
    audit = MemoryAuditSink()
    gate = ManualGate(open_)
    return OneShotDelivery(gate=gate, audit=audit, **kwargs), audit, gate


class DeliveryTest(unittest.TestCase):
    def test_put_accepts_and_take_collects_once(self):
        core, audit, gate = make()
        st, msg_id = core.put("hello")
        self.assertEqual(st, ACCEPTED)
        item = core.take()
        self.assertEqual(item, {"id": msg_id, "body": "hello"})
        self.assertIsNone(core.take())
        self.assertEqual(audit.of(ACCEPTED), [msg_id])

    def test_empty_text(self):
        core, audit, gate = make()
        for bad in ("", "   ", None):
            st, reason = core.put(bad)
            self.assertEqual(st, DROPPED)
            self.assertIn("empty-text", reason)
        self.assertIsNone(core.take())

    def test_empty_put_preserves_pending(self):
        core, audit, gate = make()
        _, msg_id = core.put("hello")
        self.assertEqual(core.put("   ")[0], DROPPED)
        self.assertEqual(core.take()["id"], msg_id)

    def test_duplicate(self):
        core, audit, gate = make()
        core.put("same")
        core.take()
        st, reason = core.put("same")
        self.assertEqual(st, DROPPED)
        self.assertIn("duplicate", reason)

    def test_duplicate_rejection_preserves_pending(self):
        core, audit, gate = make()
        core.put("hello")
        self.assertEqual(core.put("hello")[0], DROPPED)
        self.assertEqual(core.take()["body"], "hello")

    def test_gate_closed_at_put(self):
        core, audit, gate = make(open_=False)
        gate.set(False, "paused")
        st, reason = core.put("hello")
        self.assertEqual(st, DROPPED)
        self.assertIn("gate-closed", reason)
        self.assertIn("paused", reason)
        self.assertIsNone(core.take())

    def test_gate_reason_propagates(self):
        core, audit, gate = make(open_=False)
        gate.set(False, "fuse-tripped")
        _, reason = core.put("hello")
        self.assertIn("fuse-tripped", reason)
        self.assertIn("fuse-tripped", audit.of(DROPPED)[0])

    def test_take_empty_returns_none_without_audit(self):
        core, audit, gate = make()
        self.assertIsNone(core.take())
        self.assertEqual(audit.events, [])

    def test_gate_closes_between_put_and_take(self):
        core, audit, gate = make()
        self.assertEqual(core.put("hello")[0], ACCEPTED)
        gate.set(False, "paused")
        self.assertIsNone(core.take())
        drops = audit.of(DROPPED)
        self.assertTrue(any("gate-closed-at-take" in d for d in drops))

    def test_fifo_eviction_of_seen_limit(self):
        core, audit, gate = make(seen_limit=2)
        core.put("a")
        core.put("b")
        core.put("c")  # evicts "a" (FIFO), keeps "b" and "c"
        core.take()
        st_b, reason_b = core.put("b")
        self.assertEqual(st_b, DROPPED)  # "b" still remembered
        self.assertIn("duplicate", reason_b)
        st_a, _ = core.put("a")
        self.assertEqual(st_a, ACCEPTED)  # "a" forgotten
        self.assertEqual(core.take()["body"], "a")

    def test_superseded_on_overwrite(self):
        core, audit, gate = make()
        _, first_id = core.put("first")
        _, second_id = core.put("second")
        self.assertEqual(audit.of(SUPERSEDED), [first_id])
        item = core.take()
        self.assertEqual(item["id"], second_id)

    def test_settle_correct_item_delivered(self):
        core, audit, gate = make()
        _, msg_id = core.put("hello")
        item = core.take()
        st, detail = core.settle(item["id"], DELIVERED)
        self.assertEqual((st, detail), (DELIVERED, msg_id))
        self.assertEqual(audit.of(DELIVERED), [msg_id])

    def test_settle_correct_item_dropped(self):
        core, audit, gate = make()
        _, msg_id = core.put("hello")
        item = core.take()
        st, detail = core.settle(item["id"], DROPPED, "inject-failed: boom")
        self.assertEqual(st, DROPPED)
        self.assertIn("inject-failed", detail)
        self.assertEqual(len(audit.of(DROPPED)), 1)

    def test_settle_wrong_item_rejected_without_side_effects(self):
        core, audit, gate = make()
        _, msg_id = core.put("hello")
        item = core.take()
        before = list(audit.events)
        st, _ = core.settle("msg_nonexistent", DELIVERED)
        self.assertEqual(st, "rejected")
        self.assertEqual(audit.events, before)  # no phantom event
        # the real attempt is still open and can be settled
        st2, _ = core.settle(item["id"], DELIVERED)
        self.assertEqual(st2, DELIVERED)
        _ = msg_id

    def test_settle_duplicate_rejected(self):
        core, audit, gate = make()
        core.put("hello")
        item = core.take()
        self.assertEqual(core.settle(item["id"], DELIVERED)[0], DELIVERED)
        st, _ = core.settle(item["id"], DELIVERED)
        self.assertEqual(st, "rejected")
        self.assertEqual(len(audit.of(DELIVERED)), 1)  # no double event

    def test_settle_after_another_item_accepted(self):
        core, audit, gate = make()
        core.put("first")
        first = core.take()
        core.put("second")  # new pending; open attempt is still "first"
        st, _ = core.settle(first["id"], DELIVERED)
        self.assertEqual(st, DELIVERED)
        # "second" was never taken: settling it is rejected
        core.take()
        st2, _ = core.settle(first["id"], DELIVERED)
        self.assertEqual(st2, "rejected")

    def test_settle_unknown_outcome_rejected(self):
        core, audit, gate = make()
        core.put("hello")
        item = core.take()
        before = list(audit.events)
        st, _ = core.settle(item["id"], "maybe")
        self.assertEqual(st, "rejected")
        self.assertEqual(audit.events, before)
        # attempt still open
        self.assertEqual(core.settle(item["id"], DELIVERED)[0], DELIVERED)

    def test_settle_superseded_item_rejected(self):
        core, audit, gate = make()
        core.put("first")
        first = core.take()
        core.put("second")
        second = core.take()  # open attempt is now "second"
        st, _ = core.settle(first["id"], DELIVERED)
        self.assertEqual(st, "rejected")
        self.assertEqual(core.settle(second["id"], DELIVERED)[0], DELIVERED)

    def test_strip_normalization(self):
        core, audit, gate = make()
        core.put("  hello  ")
        self.assertEqual(core.take()["body"], "hello")
        st, reason = core.put("hello")
        self.assertEqual(st, DROPPED)
        self.assertIn("duplicate", reason)

    def test_audit_exception_never_breaks_slot(self):
        def bad_sink(event, detail=""):
            raise IOError("sink down")
        core = OneShotDelivery(gate=ManualGate(), audit=bad_sink)
        self.assertEqual(core.put("hello")[0], ACCEPTED)
        item = core.take()
        self.assertEqual(item["body"], "hello")
        self.assertEqual(core.settle(item["id"], DROPPED, "x")[0], DROPPED)
        core.put("again")
        item2 = core.take()
        self.assertEqual(core.settle(item2["id"], DELIVERED)[0], DELIVERED)


if __name__ == "__main__":
    unittest.main()
