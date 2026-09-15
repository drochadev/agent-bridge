"""Behavior tests for core.state.StateMachine (public contract only)."""
import unittest

from core.state import OPEN, PAUSED, SAFETY_HOLD, STOPPED, StateMachine


class StateTest(unittest.TestCase):
    def test_initial_state(self):
        self.assertEqual(StateMachine().state(), (STOPPED, "initial"))

    def test_valid_transitions(self):
        m = StateMachine()
        self.assertEqual(m.transition("open", "go")[0], OPEN)
        self.assertEqual(m.transition("pause")[0], PAUSED)
        self.assertEqual(m.transition("resume")[0], OPEN)
        self.assertEqual(m.transition("hold", "fuse")[0], SAFETY_HOLD)
        self.assertEqual(m.transition("resume")[0], OPEN)
        self.assertEqual(m.transition("stop")[0], STOPPED)
        # stop is valid from every state, incl. STOPPED itself
        self.assertEqual(m.transition("stop")[0], STOPPED)

    def test_open_from_all_runnable_states(self):
        for start, setup in (("paused", ["open", "pause"]),
                             ("safety", ["open", "hold"])):
            m = StateMachine()
            for cmd in setup:
                m.transition(cmd)
            self.assertEqual(m.state()[0],
                             PAUSED if start == "paused" else SAFETY_HOLD)
            self.assertEqual(m.transition("open")[0], OPEN)

    def test_invalid_transitions_rejected_without_corruption(self):
        m = StateMachine()  # STOPPED
        for bad in ("pause", "resume"):
            st, detail = m.transition(bad)
            self.assertEqual(st, "rejected")
            self.assertIn("invalid transition", detail)
        self.assertEqual(m.state()[0], STOPPED)
        m.transition("open")
        st, _ = m.transition("resume")  # resume from OPEN is invalid
        self.assertEqual(st, "rejected")
        self.assertEqual(m.state()[0], OPEN)
        st, _ = m.transition("explode")
        self.assertEqual(st, "rejected")

    def test_open_is_idempotent_and_records_reason(self):
        m = StateMachine()
        m.transition("open", "first")
        st, detail = m.transition("open", "second")
        self.assertEqual(st, OPEN)
        self.assertEqual(m.state(), (OPEN, "second"))
        self.assertIn("second", detail)

    def test_reason_recorded(self):
        m = StateMachine()
        m.transition("open", "operator go-ahead")
        self.assertEqual(m.state(), (OPEN, "operator go-ahead"))

    def test_no_external_side_effects(self):
        # pure object: transitions only change (state, reason)
        m = StateMachine()
        before = (m._state, m._reason)
        m.transition("pause")  # invalid from STOPPED
        self.assertEqual((m._state, m._reason), before)


if __name__ == "__main__":
    unittest.main()
