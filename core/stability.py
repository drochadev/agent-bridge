"""Stability detector: successive observations -> one finished response.

Pure and deterministic (no I/O, no clock, no external systems). Turns a
stream of observations into at most one emission per generation cycle:

  IDLE --generating--> GENERATING --finished--> EMITTED --generating--> GENERATING ...

An emission is {"text": <last non-empty text>}. Texts are stripped; empty or
non-string entries never produce a message. A finished observation is trusted
even without a prior generating one (the source asserts completion). After an
emission, further observations of the same response never re-emit; only a new
generating observation opens a new cycle.
"""
IDLE = "idle"
GENERATING = "generating"
EMITTED = "emitted"


class StabilityDetector:
    """Minimal internal state: which phase of the cycle we are in."""

    def __init__(self):
        self._phase = IDLE

    def state(self):
        """Read-only view of the current phase."""
        return self._phase

    @staticmethod
    def _last_text(texts):
        candidates = [t.strip() for t in (texts or [])
                      if isinstance(t, str) and t.strip()]
        return candidates[-1] if candidates else None

    def observe(self, generating, finished, texts):
        """Feed one observation. Returns {"text": ...} exactly once per
        finished response, else None.

        Emits when generation stops (was GENERATING, now quiet) or when the
        source asserts finished — provided there is a non-empty text. A quiet
        IDLE observation with text but no event emits nothing: nothing
        happened. After an emission, the same response never re-emits; only a
        new generating observation opens a new cycle.
        """
        generating = bool(generating)
        finished = bool(finished)
        if generating:
            self._phase = GENERATING
            return None
        if self._phase == EMITTED:
            return None  # same response: never re-emit
        was_generating = (self._phase == GENERATING)
        self._phase = EMITTED
        if not (finished or was_generating):
            return None
        text = self._last_text(texts)
        if text is None:
            return None
        return {"text": text}
