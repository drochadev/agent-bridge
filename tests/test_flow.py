"""Behavior tests for core.flow (wiring only, no I/O)."""
import unittest

from adapters.observe import ObservationFeed
from core.audit import MemoryAuditSink
from core.delivery import DELIVERED, DROPPED, OneShotDelivery
from core.flow import IDLE, Flow
from core.gate import ManualGate


def env(generating=False, finished=False, texts=None):
    return {"generating": generating, "finished": finished,
            "texts": texts if texts is not None else []}


def make(open_=True, inject=None, prove=None):
    audit = MemoryAuditSink()
    gate = ManualGate(open_)
    delivery = OneShotDelivery(gate=gate, audit=audit)
    flow = Flow(feed=ObservationFeed(), delivery=delivery,
                inject=inject if inject is not None else (lambda item: True),
                prove=prove if prove is not None else (lambda item: True))
    return flow, delivery, audit, gate


class FlowTest(unittest.TestCase):
    def test_generating_envelope_is_idle(self):
        flow, delivery, audit, _ = make()
        self.assertEqual(flow.process(env(True, False, ["part"])),
                         (IDLE, None))

    def test_idle_does_not_touch_delivery(self):
        flow, delivery, audit, _ = make()
        flow.process(env(True, False, ["part"]))
        flow.process(env(True, False, ["part"]))
        self.assertEqual(audit.events, [])
        self.assertIsNone(delivery.take())

    def test_finalization_attempts_delivery(self):
        flow, delivery, audit, _ = make()
        flow.process(env(True, False, ["part"]))
        st, detail = flow.process(env(False, True, ["done"]))
        self.assertEqual(st, DELIVERED)
        self.assertEqual(audit.of(DELIVERED), [detail])

    def test_gate_closed(self):
        flow, delivery, audit, gate = make(open_=False)
        gate.set(False, "paused")
        st, reason = flow.process(env(False, True, ["answer"]))
        self.assertEqual(st, DROPPED)
        self.assertIn("gate-closed", reason)

    def test_duplicate_text(self):
        flow, delivery, audit, _ = make()
        flow.process(env(False, True, ["one"]))
        flow.process(env(True, False, ["two"]))
        st, reason = flow.process(env(False, True, ["one"]))
        self.assertEqual(st, DROPPED)
        self.assertIn("duplicate", reason)

    def test_injector_failure(self):
        def boom(item):
            raise RuntimeError("down")
        flow, delivery, audit, _ = make(inject=boom)
        st, reason = flow.process(env(False, True, ["answer"]))
        self.assertEqual(st, DROPPED)
        self.assertIn("inject-failed", reason)

    def test_prover_false(self):
        flow, delivery, audit, _ = make(prove=lambda item: False)
        st, reason = flow.process(env(False, True, ["answer"]))
        self.assertEqual(st, DROPPED)
        self.assertIn("unproven", reason)

    def test_proven_delivery(self):
        seen = []
        flow, delivery, audit, _ = make(inject=lambda item: seen.append(item))
        st, detail = flow.process(env(False, True, ["answer"]))
        self.assertEqual(st, DELIVERED)
        self.assertEqual(seen[0]["body"], "answer")
        self.assertEqual(audit.of(DELIVERED), [detail])

    def test_flow_delegates_instead_of_reimplementing(self):
        calls = []
        feed_calls = []

        class SpyFeed:
            def observe(self, envelope):
                feed_calls.append(envelope)
                return "text-from-feed"

        class SpyDelivery:
            def put(self, text):
                calls.append(("put", text))
                return "accepted", "m1"

            def take(self):
                calls.append(("take",))
                return {"id": "m1", "body": "text-from-feed"}

            def settle(self, item_id, outcome, reason=None):
                calls.append(("settle", item_id, outcome))
                return outcome, item_id

        flow = Flow(feed=SpyFeed(), delivery=SpyDelivery(),
                    inject=lambda item: True, prove=lambda item: True)
        envelope = env(False, True, ["x"])
        self.assertEqual(flow.process(envelope)[0], DELIVERED)
        self.assertEqual(feed_calls, [envelope])
        self.assertEqual([c[0] for c in calls], ["put", "take", "settle"])

    def test_no_io_dependencies(self):
        import core.flow as mod
        source = open(mod.__file__, encoding="utf-8").read()
        for forbidden in ("socket", "http", "subprocess", "sqlite", "open(",
                          "thread", "Lifecycle", "ManualGate"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
