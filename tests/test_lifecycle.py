"""Behavior tests for core.lifecycle (public contract only, explicit clock)."""
import unittest

from core.audit import MemoryAuditSink
from core.delivery import ACCEPTED, DROPPED, OneShotDelivery
from core.fuses import Fuses
from core.lifecycle import Lifecycle
from core.state import OPEN, PAUSED, SAFETY_HOLD, STOPPED, StateMachine

NOW = 1_000_000_000_000


def rec(age_s, hash_="h", confirmed=True):
    return {"at_ms": NOW - age_s * 1000, "hash": hash_, "confirmed": confirmed}


def lifecycle(records=None, **fuse_kwargs):
    log = list(records or [])
    machine = StateMachine()
    fuses = Fuses(history=lambda: list(log), **fuse_kwargs)
    return Lifecycle(machine, fuses), machine, log


class LifecycleTest(unittest.TestCase):
    def test_open_state_and_clear_fuses_gate_open(self):
        lc, machine, _ = lifecycle()
        machine.transition("open", "go")
        self.assertIsNone(lc.poll(NOW))
        self.assertEqual(lc.gate().is_open(), (True, ""))

    def test_closed_or_stopped_state_gate_closed(self):
        lc, machine, _ = lifecycle()
        self.assertEqual(lc.gate().is_open()[0], False)  # STOPPED
        machine.transition("open")
        machine.transition("pause")
        opened, reason = lc.gate().is_open()
        self.assertFalse(opened)
        self.assertIn(PAUSED, reason)

    def test_fuse_trip_engages_safety_hold(self):
        recs = [rec(s, f"h{s}") for s in range(12)]
        lc, machine, _ = lifecycle(recs)
        machine.transition("open")
        reason = lc.poll(NOW)
        self.assertIsNotNone(reason)
        self.assertIn("turns", reason)
        self.assertEqual(machine.state()[0], SAFETY_HOLD)

    def test_gate_stays_closed_while_holding(self):
        recs = [rec(s, f"h{s}") for s in range(12)]
        lc, machine, _ = lifecycle(recs)
        machine.transition("open")
        lc.poll(NOW)
        # window passes, but the machine still holds: gate stays closed
        lc.poll(NOW + 3_600_000)
        opened, reason = lc.gate().is_open()
        self.assertFalse(opened)
        self.assertIn(SAFETY_HOLD, reason)
        self.assertEqual(machine.state()[0], SAFETY_HOLD)

    def test_gate_reason_identifies_cause(self):
        lc, machine, _ = lifecycle()
        machine.transition("open")
        _, state_reason = lc.gate().is_open()
        self.assertEqual(state_reason, "")  # open: no reason needed
        machine.transition("pause", "operator")
        _, paused_reason = lc.gate().is_open()
        self.assertIn("operator", paused_reason)

    def test_delivery_consumes_lifecycle_gate(self):
        lc, machine, _ = lifecycle()
        machine.transition("open")
        lc.poll(NOW)
        audit = MemoryAuditSink()
        delivery = OneShotDelivery(gate=lc.gate(), audit=audit)
        self.assertEqual(delivery.put("hello")[0], ACCEPTED)
        self.assertIsNotNone(delivery.take())

    def test_tripped_fuse_really_holds_state_and_blocks_delivery(self):
        recs = [rec(s, f"h{s}") for s in range(12)]
        lc, machine, _ = lifecycle(recs)
        machine.transition("open")
        audit = MemoryAuditSink()
        delivery = OneShotDelivery(gate=lc.gate(), audit=audit)
        self.assertEqual(delivery.put("before")[0], ACCEPTED)
        lc.poll(NOW)  # trip reported AND state engaged, not just reported
        self.assertEqual(machine.state()[0], SAFETY_HOLD)
        st, reason = delivery.put("after")
        self.assertEqual(st, DROPPED)
        self.assertIn("gate-closed", reason)

    def test_resume_needs_fresh_poll(self):
        recs = [rec(s, f"h{s}") for s in range(12)]
        lc, machine, log = lifecycle(recs)
        machine.transition("open")
        lc.poll(NOW)
        machine.transition("resume", "operator")
        # cache still holds the trip until the driver polls again
        self.assertFalse(lc.gate().is_open()[0])
        log.clear()  # source drains (e.g. window moved on)
        self.assertIsNone(lc.poll(NOW + 3_600_000))
        self.assertEqual(lc.gate().is_open(), (True, ""))

    def test_hold_rejected_when_stopped_keeps_state(self):
        recs = [rec(s, f"h{s}") for s in range(12)]
        lc, machine, _ = lifecycle(recs)
        reason = lc.poll(NOW)  # fuse trips, but STOPPED cannot hold
        self.assertIsNotNone(reason)
        self.assertEqual(machine.state()[0], STOPPED)
        self.assertFalse(lc.gate().is_open()[0])


if __name__ == "__main__":
    unittest.main()
