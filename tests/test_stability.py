"""Behavior tests for core.stability (pure, deterministic, explicit)."""
import unittest

from core.stability import EMITTED, GENERATING, IDLE, StabilityDetector


class StabilityTest(unittest.TestCase):
    def test_initial_generating_emits_nothing(self):
        det = StabilityDetector()
        self.assertIsNone(det.observe(True, False, ["partial"]))
        self.assertEqual(det.state(), GENERATING)

    def test_repeated_generating_emits_nothing(self):
        det = StabilityDetector()
        for _ in range(5):
            self.assertIsNone(det.observe(True, False, ["still going"]))
        self.assertEqual(det.state(), GENERATING)

    def test_generating_then_quiet_emits_once(self):
        det = StabilityDetector()
        det.observe(True, False, ["part"])
        out = det.observe(False, False, ["done"])
        self.assertEqual(out, {"text": "done"})
        self.assertIsNone(det.observe(False, False, ["done"]))

    def test_finished_flag_emits(self):
        det = StabilityDetector()
        out = det.observe(False, True, ["answer"])
        self.assertEqual(out, {"text": "answer"})
        self.assertEqual(det.state(), EMITTED)

    def test_identical_repeats_never_duplicate(self):
        det = StabilityDetector()
        det.observe(False, True, ["answer"])
        for _ in range(3):
            self.assertIsNone(det.observe(False, True, ["answer"]))

    def test_same_response_after_emit_stays_silent(self):
        det = StabilityDetector()
        det.observe(True, False, ["part"])
        det.observe(False, True, ["done"])
        self.assertIsNone(det.observe(False, True, ["done"]))
        self.assertIsNone(det.observe(False, False, ["done"]))

    def test_new_generation_after_finish_can_emit_again(self):
        det = StabilityDetector()
        det.observe(True, False, ["one"])
        self.assertEqual(det.observe(False, True, ["one"]),
                         {"text": "one"})
        det.observe(True, False, ["two"])
        self.assertEqual(det.observe(False, True, ["two"]),
                         {"text": "two"})

    def test_empty_or_invalid_text_emits_nothing(self):
        det = StabilityDetector()
        self.assertIsNone(det.observe(True, False, []))
        self.assertIsNone(det.observe(False, True, []))
        self.assertIsNone(det.observe(False, True, ["", "   ", None, 42]))
        self.assertIsNone(det.observe(False, True, None))

    def test_multiple_texts_last_non_empty_wins(self):
        det = StabilityDetector()
        out = det.observe(False, True, ["first", "", "second", "   "])
        self.assertEqual(out, {"text": "second"})
        det2 = StabilityDetector()
        out2 = det2.observe(True, False, ["a"])
        self.assertIsNone(out2)
        out2 = det2.observe(False, False, ["a", "b"])
        self.assertEqual(out2, {"text": "b"})

    def test_finished_without_prior_generating_emits(self):
        # unexpected sequence: source asserts completion with no history.
        # The detector trusts the source and emits exactly once.
        det = StabilityDetector()
        self.assertEqual(det.state(), IDLE)
        out = det.observe(False, True, ["late answer"])
        self.assertEqual(out, {"text": "late answer"})
        self.assertIsNone(det.observe(False, True, ["late answer"]))

    def test_quiet_idle_with_text_but_no_event_emits_nothing(self):
        det = StabilityDetector()
        self.assertIsNone(det.observe(False, False, ["static text"]))
        self.assertEqual(det.state(), EMITTED)


if __name__ == "__main__":
    unittest.main()
