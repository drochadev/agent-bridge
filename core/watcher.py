"""Watcher: one poll cycle over a Source, delivered through an Intake.

Thin cycle seam, no rules of its own:

    Watcher
      └── Intake
            └── Source

The Watcher owns the polling rhythm (one process() per poll) and holds the
adopted token privately via its Intake; all transform dispositions
(skipped/no-message/invalid/accepted/rejected) and the adoption rule live in
Intake. Failures propagate with the token unadopted, so the next poll
retries the same versions. No clock, no I/O, no retry policy, no transport.
"""
from core.intake import Intake


class Watcher:
    """Binds one source to one deliver callable through an Intake."""

    def __init__(self, source, deliver):
        self._intake = Intake(source, deliver)

    def poll(self):
        """Run exactly one cycle. Returns [{id, version, disposition}]."""
        return self._intake.process()

    def token(self):
        """Read-only view of the adopted token (None before first adoption)."""
        return self._intake.token()
