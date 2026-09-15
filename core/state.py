"""Operational state machine: STOPPED | OPEN | PAUSED | SAFETY_HOLD.

Faithful extraction of the proven transition table. Pure in-memory object:
no persistence, no I/O, no delivery side effects — no transition delivers,
re-offers, or clears anything. Thread-safety: not thread-safe (like the rest
of the core).

Commands mirror the proven set, plus "hold": the private system reaches the
safety state via a direct store update when a fuse trips; the public machine
exposes that as an explicit command so the upper layer can engage safety
without touching internals.
"""
STOPPED = "stopped"
OPEN = "open"
PAUSED = "paused"
SAFETY_HOLD = "safety_hold"

_VALID = {
    "open": (STOPPED, PAUSED, SAFETY_HOLD, OPEN),
    "resume": (PAUSED, SAFETY_HOLD),
    "pause": (OPEN,),
    "hold": (OPEN, PAUSED),
    "stop": (OPEN, PAUSED, SAFETY_HOLD, STOPPED),
}
_RESULT = {
    "open": OPEN,
    "resume": OPEN,
    "pause": PAUSED,
    "hold": SAFETY_HOLD,
    "stop": STOPPED,
}


class StateMachine:
    """Single current state with a reason. Starts STOPPED."""

    def __init__(self):
        self._state = STOPPED
        self._reason = "initial"

    def state(self):
        """Return (state, reason). Read-only."""
        return self._state, self._reason

    def transition(self, command, reason=""):
        """Apply a command. Returns (state, detail).

        Valid transitions move to the target state and record the reason
        ("open" onto OPEN is idempotent: it stays OPEN and records the reason).
        Invalid transitions are rejected with ("rejected", detail) and leave
        the state untouched.
        """
        if command not in _VALID:
            return "rejected", f"unknown command: {command}"
        if self._state not in _VALID[command]:
            return "rejected", (
                f"invalid transition: {self._state} -> {command}")
        self._state = _RESULT[command]
        self._reason = reason or command
        return self._state, self._reason
