"""Behavior tests for core.policy.attempt_once (public contract only)."""
import unittest

from core.audit import MemoryAuditSink
from core.delivery import DELIVERED, DROPPED, OneShotDelivery
from core.gate import ManualGate
from core.policy import attempt_once


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


if __name__ == "__main__":
    unittest.main()
