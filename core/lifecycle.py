"""Lifecycle: Fuses -> StateMachine -> Gate -> Delivery.

Small coordination layer with no new domain logic. The caller drives time
explicitly via poll(now_ms) — typically once per driver cycle, before using
the gate. The gate therefore reflects the machine state plus the most recent
fuse evaluation (never a hidden clock).

Separation (mirrors the proven system):
  Fuses detect (check -> reason | None, no state touched);
  StateMachine holds the state (transitions only);
  Lifecycle coordinates (poll engages SAFETY_HOLD on trip);
  Gate exposes the decision (open/closed + reason);
  Delivery applies it (accepts a Gate, knows nothing above it).
"""
from core.state import OPEN, StateMachine


class Lifecycle:
    """Coordinates one machine and one fuse set. Not thread-safe."""

    def __init__(self, machine: StateMachine, fuses):
        self._machine = machine
        self._fuses = fuses
        self._last_fuse_reason = None

    def poll(self, now_ms: int):
        """Evaluate fuses once. On trip, engage SAFETY_HOLD.

        Returns the trip reason, or None when clear. Always refreshes the
        cached evaluation the gate reads.
        """
        reason = self._fuses.check(now_ms)
        self._last_fuse_reason = reason
        if reason is not None:
            self._machine.transition("hold", reason)
        return reason

    def state(self):
        """Read-only view of (state, reason)."""
        return self._machine.state()

    def last_fuse_reason(self):
        """Most recent fuse evaluation (None when clear)."""
        return self._last_fuse_reason

    def gate(self):
        """A Gate over this lifecycle. Open only when the machine is OPEN
        and the last fuse evaluation was clear."""
        lifecycle = self

        class _LifecycleGate:
            def is_open(self):
                state, sreason = lifecycle.state()
                if state != OPEN:
                    return False, f"not-open: {state} ({sreason})"
                freason = lifecycle.last_fuse_reason()
                if freason is not None:
                    return False, freason
                return True, ""

        return _LifecycleGate()
