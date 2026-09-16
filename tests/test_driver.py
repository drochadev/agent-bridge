"""Behavior tests for core.driver (explicit clock, no loops/threads)."""
import unittest

from core.audit import MemoryAuditSink
from core.delivery import ACCEPTED, DROPPED, OneShotDelivery
from core.driver import Driver
from core.fuses import Fuses
from core.lifecycle import Lifecycle
from core.state import OPEN, SAFETY_HOLD, StateMachine

NOW = 1_000_000_000_000


def rec(age_s, hash_="h", confirmed=True):
    return {"at_ms": NOW - age_s * 1000, "hash": hash_, "confirmed": confirmed}


def setup(records=None, **fuse_kwargs):
    log = list(records or [])
    machine = StateMachine()
    machine.transition("open", "go")
    lifecycle = Lifecycle(machine,
                          Fuses(history=lambda: list(log), **fuse_kwargs))
    return Driver(lifecycle), lifecycle, machine, log


class DriverTest(unittest.TestCase):
    def test_run_once_updates_evaluation(self):
        driver, lifecycle, machine, _ = setup()
        self.assertIsNone(driver.run_once(NOW))
        self.assertEqual(machine.state()[0], OPEN)

    def test_fuse_trips_through_driver(self):
        recs = [rec(s, f"h{s}") for s in range(12)]
        driver, lifecycle, machine, _ = setup(recs)
        reason = driver.run_once(NOW)  # no direct lifecycle.poll() here
        self.assertIsNotNone(reason)
        self.assertIn("turns", reason)
        self.assertEqual(machine.state()[0], SAFETY_HOLD)

    def test_resume_then_run_once_refreshes(self):
        recs = [rec(s, f"h{s}") for s in range(12)]
        driver, lifecycle, machine, log = setup(recs)
        driver.run_once(NOW)
        machine.transition("resume", "operator")
        log.clear()
        self.assertIsNone(driver.run_once(NOW + 3_600_000))
        # delivery sees the refreshed open gate
        audit = MemoryAuditSink()
        delivery = OneShotDelivery(
            gate=lifecycle.gate(), audit=audit)
        self.assertEqual(delivery.put("hello")[0], ACCEPTED)

    def test_delivery_gate_matches_updated_state(self):
        recs = [rec(s, f"h{s}") for s in range(12)]
        driver, lifecycle, machine, _ = setup(recs)
        audit = MemoryAuditSink()
        delivery = OneShotDelivery(
            gate=lifecycle.gate(), audit=audit)
        driver.run_once(NOW)  # trip -> hold
        st, reason = delivery.put("hello")
        self.assertEqual(st, DROPPED)
        self.assertIn("gate-closed", reason)

    def test_no_hidden_time(self):
        # same input, same output, twice: fully determined by arguments
        driver, _, _, _ = setup()
        self.assertEqual(driver.run_once(NOW), driver.run_once(NOW))
        # advancing the clock is the ONLY thing that can change the outcome
        recs = [rec(s, f"h{s}") for s in range(12)]
        driver2, _, _, _ = setup(recs)
        self.assertIsNotNone(driver2.run_once(NOW))


if __name__ == "__main__":
    unittest.main()
