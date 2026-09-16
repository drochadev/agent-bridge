"""Web-to-agent flow: finished text -> one delivery attempt.

Pure wiring, no rules of its own: asks the feed for finished text and, only
when there is one, runs the attempt_once policy over the delivery slot. Gate,
dedupe, settle, audit, validation and stability all live in the composed
pieces — this class only propagates. Knows nothing about lifecycles, HTTP,
browsers, agents, or I/O.
"""
from core.policy import attempt_once

IDLE = "idle"


class Flow:
    """Holds feed + delivery + transport. process() drives one envelope."""

    def __init__(self, feed, delivery, inject, prove):
        self._feed = feed
        self._delivery = delivery
        self._inject = inject
        self._prove = prove

    def process(self, envelope):
        """Returns ("idle", None) without touching delivery, or the
        attempt_once result (status, detail) verbatim."""
        text = self._feed.observe(envelope)
        if text is None:
            return IDLE, None
        return attempt_once(self._delivery, text, self._inject, self._prove)
