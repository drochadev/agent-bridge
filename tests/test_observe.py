"""Behavior tests for adapters.observe (composition only, no I/O)."""
import unittest

from adapters.observe import ObservationFeed
from core.envelope import ValidationError


def env(generating=False, finished=False, texts=None, **extra):
    body = {"generating": generating, "finished": finished,
            "texts": texts if texts is not None else []}
    body.update(extra)
    return body


class ObserveTest(unittest.TestCase):
    def test_generating_envelope_gives_none(self):
        feed = ObservationFeed()
        self.assertIsNone(feed.observe(env(True, False, ["part"])))

    def test_generating_sequence_gives_none(self):
        feed = ObservationFeed()
        for _ in range(4):
            self.assertIsNone(feed.observe(env(True, False, ["part"])))

    def test_finalization_gives_text(self):
        feed = ObservationFeed()
        feed.observe(env(True, False, ["part"]))
        self.assertEqual(feed.observe(env(False, False, ["done"])), "done")

    def test_finished_flag_gives_text(self):
        feed = ObservationFeed()
        self.assertEqual(feed.observe(env(False, True, ["answer"])), "answer")

    def test_repeated_finished_observation_no_duplicate(self):
        feed = ObservationFeed()
        self.assertEqual(feed.observe(env(False, True, ["answer"])), "answer")
        self.assertIsNone(feed.observe(env(False, True, ["answer"])))
        self.assertIsNone(feed.observe(env(False, True, ["answer"])))

    def test_new_generation_allows_new_finalization(self):
        feed = ObservationFeed()
        self.assertEqual(feed.observe(env(False, True, ["one"])), "one")
        self.assertIsNone(feed.observe(env(True, False, ["two"])))
        self.assertEqual(feed.observe(env(False, True, ["two"])), "two")

    def test_invalid_envelope_raises_validation_error(self):
        feed = ObservationFeed()
        for bad in ({}, {"texts": "nope"}, {"texts": [7]},
                    {"generating": "yes", "texts": []}, None, [1]):
            with self.assertRaises(ValidationError):
                feed.observe(bad)

    def test_unknown_metadata_does_not_change_result(self):
        feed = ObservationFeed()
        out = feed.observe(env(False, True, ["answer"], composer={},
                               human={}, ext_v="9", url="https://x"))
        self.assertEqual(out, "answer")

    def test_empty_texts_follow_detector_contract(self):
        feed = ObservationFeed()
        self.assertIsNone(feed.observe(env(False, True, [])))
        self.assertIsNone(feed.observe(env(False, True, ["", "  "])))

    def test_composition_validate_then_detect(self):
        # feed adds no rules of its own: same inputs through validate +
        # StabilityDetector directly must produce the same outputs.
        from core.envelope import validate
        from core.stability import StabilityDetector
        feed = ObservationFeed()
        detector = StabilityDetector()
        sequence = [env(True, False, ["a"]),
                    env(True, False, ["ab"]),
                    env(False, True, ["abc"]),
                    env(False, True, ["abc"])]
        for envelope in sequence:
            expected_obs = validate(envelope)
            expected = detector.observe(expected_obs["generating"],
                                        expected_obs["finished"],
                                        expected_obs["texts"])
            expected_text = expected["text"] if expected else None
            self.assertEqual(feed.observe(envelope), expected_text)

    def test_adapter_touches_no_delivery_or_io(self):
        import adapters.observe as mod
        source = open(mod.__file__, encoding="utf-8").read()
        for forbidden in ("delivery", "Delivery", "http.server", "socket",
                          "subprocess", "sqlite", "open(", "Chrome"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
