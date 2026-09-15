"""Safety fuses: pure counters over confirmed deliveries.

Faithful extraction of the three proven fuses (turn limit, rate limit,
content repetition). Fuses never touch a state machine: check() returns a
reason string when tripped, None when clear. The upper layer decides what to
do with it (e.g. engage SAFETY_HOLD and keep holding it — that persistence is
the latch; the fuse itself is stateless and re-evaluates the same data the
same way on every call).

Source contract: a callable returning an iterable of records, each a mapping
with "at_ms" (epoch ms), "hash" (content id), "confirmed" (bool). Only
confirmed records count — unconfirmed ones are ignored by the fuse, not by
trust.

Windows are explicit seconds; a record counts when
(now_ms - at_ms) <= window — mirroring the proven code, which also counts
records dated in the future. Controlled sources should never produce them.
"""
from typing import Callable, Iterable, Mapping, Optional


class Fuses:
    """Three independent fuses, evaluated in order: turns, rate, repetition."""

    def __init__(self, source: Callable[[], Iterable[Mapping]],
                 turns_n: int = 12, turns_s: int = 600,
                 rate_n: int = 6, rate_s: int = 60,
                 repeat_n: int = 3):
        self._source = source
        self._turns_n = turns_n
        self._turns_s = turns_s
        self._rate_n = rate_n
        self._rate_s = rate_s
        self._repeat_n = repeat_n

    def _confirmed(self):
        return [r for r in self._source() if r.get("confirmed")]

    @staticmethod
    def _in_window(records, now_ms, window_s):
        return [r for r in records
                if now_ms - r["at_ms"] <= window_s * 1000]

    def check(self, now_ms: int) -> Optional[str]:
        """Return a trip reason, or None when all fuses are clear."""
        confirmed = self._confirmed()
        turns = self._in_window(confirmed, now_ms, self._turns_s)
        if len(turns) >= self._turns_n:
            return (f"fuse turns: {len(turns)} deliveries "
                    f"in {self._turns_s}s")
        rate = self._in_window(confirmed, now_ms, self._rate_s)
        if len(rate) >= self._rate_n:
            return (f"fuse rate: {len(rate)} deliveries "
                    f"in {self._rate_s}s")
        recent = sorted(confirmed, key=lambda r: r["at_ms"], reverse=True)
        recent = recent[:self._repeat_n]
        if len(recent) == self._repeat_n and len({r["hash"] for r in recent}) == 1:
            return (f"fuse repetition: same content "
                    f"{self._repeat_n}x in a row")
        return None
