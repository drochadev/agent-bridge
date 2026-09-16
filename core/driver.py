"""Operational driver: one explicit cycle at a time.

A Driver owns a Lifecycle and advances it exactly once per run_once(now_ms)
call: evaluate fuses (engaging SAFETY_HOLD on trip) so gate/state are current
for delivery. No loops, no threads, no sleep, no I/O, no hidden clock — the
caller supplies now_ms, which keeps every cycle deterministic and testable.

Later layers (schedulers, watchers, persistence hooks) plug in around this
seam; the driver itself must never duplicate Lifecycle rules.
"""
from core.lifecycle import Lifecycle


class Driver:
    """Minimal cycle orchestrator over one Lifecycle."""

    def __init__(self, lifecycle: Lifecycle):
        self._lifecycle = lifecycle

    def run_once(self, now_ms: int):
        """Run exactly one cycle. Returns the trip reason, or None."""
        return self._lifecycle.poll(now_ms)
