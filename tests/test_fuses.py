"""Behavior tests for core.fuses.Fuses (public contract only)."""
import unittest

from core.fuses import Fuses

NOW = 1_000_000_000_000


def rec(age_s, hash_="h", confirmed=True):
    return {"at_ms": NOW - age_s * 1000, "hash": hash_, "confirmed": confirmed}


def make(records, **kwargs):
    return Fuses(source=lambda: list(records), **kwargs)


class FusesTest(unittest.TestCase):
    def test_empty_source_is_clear(self):
        self.assertIsNone(make([]).check(NOW))

    def test_turns_fuse_below_and_above(self):
        # spread over 100-111s ago: inside the 600s window, outside the 60s one
        below = [rec(100 + s, f"h{s}") for s in range(11)]
        self.assertIsNone(make(below).check(NOW))
        above = [rec(100 + s, f"h{s}") for s in range(12)]
        reason = make(above).check(NOW)
        self.assertIsNotNone(reason)
        self.assertIn("turns", reason)

    def test_turns_window_boundary(self):
        at_edge = [rec(600, f"h{i}") for i in range(12)]  # exactly 600s: counts
        self.assertIsNotNone(make(at_edge).check(NOW))
        outside = [rec(601, f"h{i}") for i in range(12)]  # 601s: out
        self.assertIsNone(make(outside, repeat_n=99).check(NOW))

    def test_rate_fuse_isolated(self):
        recs = [rec(s, f"h{s}") for s in range(6)]  # 6 in 60s
        fuses = make(recs, turns_n=9999)
        reason = fuses.check(NOW)
        self.assertIsNotNone(reason)
        self.assertIn("rate", reason)
        self.assertIsNone(make(recs[:5], turns_n=9999).check(NOW))

    def test_repetition_fuse(self):
        same3 = [rec(1, "x"), rec(2, "x"), rec(3, "x")]
        reason = make(same3, turns_n=9999, rate_n=9999).check(NOW)
        self.assertIsNotNone(reason)
        self.assertIn("repetition", reason)
        mixed = [rec(1, "x"), rec(2, "y"), rec(3, "x")]
        self.assertIsNone(make(mixed, turns_n=9999, rate_n=9999).check(NOW))
        short = [rec(1, "x"), rec(2, "x")]  # fewer than repeat_n
        self.assertIsNone(make(short, turns_n=9999, rate_n=9999).check(NOW))

    def test_unconfirmed_events_do_not_count(self):
        recs = [rec(s, f"h{s}", confirmed=False) for s in range(12)]
        self.assertIsNone(make(recs).check(NOW))
        mixed = ([rec(s, "same", confirmed=False) for s in range(5)]
                 + [rec(1, "a"), rec(2, "b")])
        self.assertIsNone(make(mixed, turns_n=9999, rate_n=9999).check(NOW))

    def test_sticky_while_condition_holds(self):
        recs = [rec(s, f"h{s}") for s in range(12)]
        fuses = make(recs)
        first = fuses.check(NOW)
        second = fuses.check(NOW + 30_000)  # still inside the window
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)

    def test_configurable_parameters(self):
        recs = [rec(1, "a"), rec(2, "b")]
        self.assertIsNotNone(make(recs, turns_n=2, turns_s=60).check(NOW))
        self.assertIsNone(make(recs, turns_n=3, turns_s=60).check(NOW))
        same2 = [rec(1, "z"), rec(2, "z")]
        self.assertIsNotNone(make(same2, turns_n=9999, rate_n=9999,
                                  repeat_n=2).check(NOW))
        self.assertIsNone(make(same2, turns_n=9999, rate_n=9999,
                               repeat_n=3).check(NOW))

    def test_first_trip_wins_order(self):
        recs = [rec(s, "same") for s in range(12)]  # trips turns AND repetition
        reason = make(recs).check(NOW)
        self.assertIn("turns", reason)  # turns evaluated first


if __name__ == "__main__":
    unittest.main()
