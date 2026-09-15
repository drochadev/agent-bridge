"""Behavior tests for core.activity.classify (public contract only)."""
import copy
import unittest

from core.activity import COMPLETED, RUNNING, WAITING, classify

AGORA = 1_000_000_000_000


def sess(upd):
    return {"time_updated": upd}


def r(i, role, c):
    return {"id": i, "role": role, "created": c}


def run(mid, tool, c):
    return {"message_id": mid, "tool": tool, "created": c}


def snap(roles, running, n_parts, session, part_types=None):
    return {"roles": roles, "running": running, "n_parts": n_parts,
            "session": session,
            "part_types": part_types or {}}


class ActivityTest(unittest.TestCase):
    # --- transcription of the 9 proven selftest cases ---
    def test_empty_snapshot(self):
        v, _ = classify(snap([], [], 0, sess(AGORA - 999_000)), now_ms=AGORA)
        self.assertEqual(v, WAITING)

    def test_last_message_from_user(self):
        s = snap([r("m1", "user", 100)], [], 1, sess(AGORA - 999_000))
        v, why = classify(s, now_ms=AGORA)
        self.assertEqual(v, WAITING)
        self.assertIn("user", why)

    def test_running_tool_in_turn(self):
        s = snap([r("m1", "user", 100), r("m2", "assistant", 200)],
                 [run("m2", "bash", 300)], 2, sess(AGORA - 5_000),
                 {"step-start": 1})
        v, why = classify(s, now_ms=AGORA)
        self.assertEqual(v, RUNNING)
        self.assertIn("bash", why)

    def test_fresh_plain_text(self):
        s = snap([r("m1", "user", 100), r("m2", "assistant", 200)],
                 [], 3, sess(AGORA - 10_000),
                 {"step-start": 1, "step-finish": 1})
        v, _ = classify(s, now_ms=AGORA)
        self.assertEqual(v, RUNNING)

    def test_idle_completed(self):
        s = snap([r("m1", "user", 100), r("m2", "assistant", 200)],
                 [], 5, sess(AGORA - 120_000),
                 {"step-start": 1, "step-finish": 1})
        v, why = classify(s, now_ms=AGORA)
        self.assertEqual(v, COMPLETED)
        self.assertIn("idle 120s", why)

    def test_stale_running_ignored(self):
        s = snap([r("m0", "assistant", 50), r("m1", "user", 100),
                  r("m2", "assistant", 200)],
                 [run("m0", "bash", 60)], 8, sess(AGORA - 120_000),
                 {"step-start": 2, "step-finish": 2})
        v, why = classify(s, now_ms=AGORA)
        self.assertEqual(v, COMPLETED)
        self.assertIn("1 stale ignored", why)

    def test_fossil_residual_does_not_hold(self):
        fossil = AGORA - 20 * 60_000
        s = snap([r("m1", "user", 100), r("m2", "assistant", 200)],
                 [run("m2", "bash", fossil)], 5, sess(fossil),
                 {"step-start": 1, "step-finish": 1})
        v, why = classify(s, now_ms=AGORA)
        self.assertEqual(v, COMPLETED)
        self.assertIn("1 residual ignored", why)

    def test_mixed_current_wins(self):
        s = snap([r("m0", "assistant", 50), r("m1", "user", 100),
                  r("m2", "assistant", 200)],
                 [run("m0", "bash", 60), run("m2", "read", AGORA - 5_000)],
                 8, sess(AGORA - 5_000), {"step-start": 2})
        v, why = classify(s, now_ms=AGORA)
        self.assertEqual(v, RUNNING)
        self.assertIn("1 stale ignored", why)

    def test_clock_is_injected(self):
        s = snap([r("m1", "user", 100)], [], 1, sess(AGORA - 999_000))
        with self.assertRaises(TypeError):
            classify(s)  # now_ms is required
        v1, _ = classify(s, now_ms=AGORA)
        v2, _ = classify(s, now_ms=AGORA + 3_600_000)
        self.assertEqual((v1, v2), (WAITING, WAITING))

    # --- public-contract extras ---
    def test_input_snapshot_not_mutated(self):
        s = snap([r("m0", "assistant", 50), r("m1", "user", 100),
                  r("m2", "assistant", 200)],
                 [run("m0", "bash", 60)], 8, sess(AGORA - 120_000))
        before = copy.deepcopy(s)
        classify(s, now_ms=AGORA)
        self.assertEqual(s, before)
        self.assertNotIn("stale_running", s)
        self.assertNotIn("residual_running", s)

    def test_fresh_s_changes_result_predictably(self):
        s = snap([r("m1", "user", 100), r("m2", "assistant", 200)],
                 [], 3, sess(AGORA - 10_000))
        v_wide, _ = classify(s, now_ms=AGORA, fresh_s=15)
        v_narrow, _ = classify(s, now_ms=AGORA, fresh_s=5)
        self.assertEqual(v_wide, RUNNING)      # 10s < 15s: fresh
        self.assertEqual(v_narrow, COMPLETED)  # 10s > 5s: idle

    def test_residual_min_s_changes_treatment(self):
        fossil = AGORA - 20 * 60_000
        s = snap([r("m1", "user", 100), r("m2", "assistant", 200)],
                 [run("m2", "bash", fossil)], 5, sess(fossil))
        v_strict, why_strict = classify(s, now_ms=AGORA,
                                        residual_min_s=900)
        v_loose, _ = classify(s, now_ms=AGORA, residual_min_s=3600)
        self.assertEqual(v_strict, COMPLETED)  # 20min > 15min: residual
        self.assertIn("residual ignored", why_strict)
        self.assertEqual(v_loose, RUNNING)     # 20min < 60min: still live

    def test_reasons_carry_no_private_data(self):
        s = snap([r("m9", "user", 100), r("m2", "assistant", 200)],
                 [run("m9", "bash", 50)], 4, sess(AGORA - 999_000))
        _, why = classify(s, now_ms=AGORA)
        for forbidden in ("m9", "m2", "Diogo", "Pedro"):
            self.assertNotIn(forbidden, why)


if __name__ == "__main__":
    unittest.main()
