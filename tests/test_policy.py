"""Behavior tests for core.policy (public contract only)."""
import unittest

from core.audit import MemoryAuditSink
from core.delivery import DELIVERED, DROPPED, OneShotDelivery
from core.gate import ManualGate
from core.policy import EMPTY, attempt_once, take_attempt


def make(open_=True, inject=None, prove=None, **kwargs):
    audit = MemoryAuditSink()
    gate = ManualGate(open_)
    core = OneShotDelivery(gate=gate, audit=audit, **kwargs)
    return core, audit, gate, (
        inject if inject is not None else (lambda item: True),
        prove if prove is not None else (lambda item: True),
    )


class PolicyTest(unittest.TestCase):
    def test_success(self):
        core, audit, gate, (inject, prove) = make()
        self.assertEqual(attempt_once(core, "hello", inject, prove)[0], DELIVERED)
        self.assertEqual(len(audit.of(DELIVERED)), 1)
        self.assertIsNone(core.take())

    def test_inject_returning_none_still_succeeds(self):
        calls = []
        core, audit, gate, (_, prove) = make()
        st, _ = attempt_once(core, "hello",
                             lambda item: calls.append(item) or None, prove)
        self.assertEqual(st, DELIVERED)
        self.assertEqual(len(calls), 1)

    def test_put_rejection_short_circuits(self):
        core, audit, gate, (inject, prove) = make()
        for bad in ("", "   "):
            st, reason = attempt_once(core, bad, inject, prove)
            self.assertEqual(st, DROPPED)
            self.assertIn("empty-text", reason)

    def test_gate_closed(self):
        core, audit, gate, (inject, prove) = make(open_=False)
        gate.set(False, "paused")
        st, reason = attempt_once(core, "hello", inject, prove)
        self.assertEqual(st, DROPPED)
        self.assertIn("gate-closed", reason)

    def test_injector_exception(self):
        def boom(item):
            raise RuntimeError("no window")
        core, audit, gate, (_, prove) = make()
        st, reason = attempt_once(core, "hello", boom, prove)
        self.assertEqual(st, DROPPED)
        self.assertIn("inject-failed", reason)
        self.assertIn("RuntimeError", reason)
        self.assertIsNone(core.take())
        self.assertEqual(len(audit.of(DROPPED)), 1)

    def test_prove_falsy_and_exception(self):
        core, audit, gate, (inject, _) = make()
        st, reason = attempt_once(core, "a", inject, lambda item: False)
        self.assertEqual(st, DROPPED)
        self.assertIn("unproven", reason)

        def boom(item):
            raise ValueError("db gone")
        core2, audit2, _, (inject2, _) = make()
        st2, reason2 = attempt_once(core2, "b", inject2, boom)
        self.assertEqual(st2, DROPPED)
        self.assertIn("prove-failed", reason2)
        self.assertEqual(len(audit2.of(DELIVERED)), 0)

    def test_success_and_failure_audits(self):
        ok, ok_audit, _, (i_ok, p_ok) = make()
        attempt_once(ok, "yes", i_ok, p_ok)
        bad, bad_audit, _, __ = make()
        attempt_once(bad, "no", lambda item: 1 / 0, lambda item: True)
        self.assertEqual(len(ok_audit.of(DELIVERED)), 1)
        self.assertEqual(len(ok_audit.of(DROPPED)), 0)
        self.assertEqual(len(bad_audit.of(DELIVERED)), 0)
        self.assertEqual(len(bad_audit.of(DROPPED)), 1)


def stage(text="hello", open_=True):
    audit = MemoryAuditSink()
    gate = ManualGate(open_)
    delivery = OneShotDelivery(gate=gate, audit=audit)
    return delivery, audit, gate


class TakeAttemptTest(unittest.TestCase):
    def test_empty_slot(self):
        delivery, audit, _ = stage()
        self.assertEqual(take_attempt(delivery, lambda i: True,
                                      lambda i: True),
                         (EMPTY, None))
        self.assertEqual(audit.events, [])  # no delivery event generated

    def test_inject_and_prove_true_delivers(self):
        delivery, audit, _ = stage()
        delivery.put("hello")
        st, detail = take_attempt(delivery, lambda i: True, lambda i: True)
        self.assertEqual(st, DELIVERED)
        self.assertEqual(audit.of(DELIVERED), [detail])

    def test_prove_false_drops_unproven(self):
        delivery, audit, _ = stage()
        delivery.put("hello")
        st, reason = take_attempt(delivery, lambda i: True,
                                  lambda i: False)
        self.assertEqual(st, DROPPED)
        self.assertIn("unproven", reason)

    def test_injector_raises(self):
        def boom(item):
            raise RuntimeError("down")

        delivery, audit, _ = stage()
        delivery.put("hello")
        st, reason = take_attempt(delivery, boom, lambda i: True)
        self.assertEqual(st, DROPPED)
        self.assertIn("inject-failed", reason)
        self.assertIn("RuntimeError", reason)

    def test_prover_raises(self):
        def boom(item):
            raise ValueError("gone")

        delivery, audit, _ = stage()
        delivery.put("hello")
        st, reason = take_attempt(delivery, lambda i: True, boom)
        self.assertEqual(st, DROPPED)
        self.assertIn("prove-failed", reason)

    def test_take_once(self):
        delivery, audit, _ = stage()
        delivery.put("hello")
        self.assertEqual(take_attempt(delivery, lambda i: True,
                                      lambda i: True)[0], DELIVERED)
        self.assertEqual(take_attempt(delivery, lambda i: True,
                                      lambda i: True), (EMPTY, None))

    def test_correct_item_reaches_inject_and_prove(self):
        seen = {}
        delivery, _, _ = stage()
        _, msg_id = delivery.put("hello")

        def inject(item):
            seen["inject"] = dict(item)

        def prove(item):
            seen["prove"] = dict(item)
            return True

        take_attempt(delivery, inject, prove)
        self.assertEqual(seen["inject"]["id"], msg_id)
        self.assertEqual(seen["inject"]["body"], "hello")
        self.assertEqual(seen["prove"], seen["inject"])

    def test_settle_happens_once(self):
        delivery, audit, _ = stage()
        delivery.put("hello")
        take_attempt(delivery, lambda i: True, lambda i: True)
        self.assertEqual(len(audit.of(DELIVERED)), 1)
        self.assertEqual(len(audit.of(DROPPED)), 0)

    def test_exception_leaves_no_open_attempt(self):
        delivery, audit, _ = stage()
        delivery.put("hello")

        def boom(item):
            raise RuntimeError("x")

        take_attempt(delivery, boom, lambda i: True)
        # slot empty and no attempt left open: a later take/settle is clean
        self.assertIsNone(delivery.take())
        st, _ = delivery.settle("msg_nope", DROPPED, "x")
        self.assertEqual(st, "rejected")

    def test_gate_closed_at_take(self):
        # take() reports None both when empty and when the gate drops at
        # take time; take_attempt honestly returns EMPTY in both cases while
        # take() itself audits the gate drop. Same contract as the slot's
        # take/null duality.
        delivery, audit, gate = stage()
        delivery.put("hello")
        gate.set(False, "paused")
        st, _ = take_attempt(delivery, lambda i: True, lambda i: True)
        self.assertEqual(st, EMPTY)
        drops = audit.of(DROPPED)
        self.assertTrue(any("gate-closed-at-take" in d for d in drops))

    def test_no_duplicated_delivery_logic(self):
        import core.policy as mod
        source = open(mod.__file__, encoding="utf-8").read()
        body = source.split("def take_attempt", 1)[1]
        for forbidden in ("sha256", "ManualGate", "_seen", "_pending",
                          "sorted(", "attempts"):
            self.assertNotIn(forbidden, body)


if __name__ == "__main__":
    unittest.main()
