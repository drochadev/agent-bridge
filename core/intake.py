"""Intake: source changes -> transportable messages -> deliver().

Holds the adopted token internally. One process() pass: fetch changes since
the token, and for each item (in source order) reach exactly one terminal
disposition:

  final=False            -> "skipped"  (stays eligible via future versions)
  final, no block        -> "no-message"
  final, malformed block -> "invalid-message" (opening marker without content)
  block + deliver ok     -> "accepted" | "rejected" (whatever deliver says)

The token is adopted only when the whole pass completes without an
unexpected exception; rejections are terminal dispositions, not errors, so
they do not block adoption. No retry lives here: redelivery, if ever wanted,
is a future layer's decision.

"Malformed" is detected by the presence of the canonical opening marker
without an extractable block. The literal mirrors core.protocol's canonical
form and exists only to tell "tried to be a message" apart from "not a
message"; all block rules stay in protocol.
"""
from core.delivery import ACCEPTED
from core.protocol import extract_block

SKIPPED = "skipped"
NO_MESSAGE = "no-message"
INVALID_MESSAGE = "invalid-message"

# Mirrors the canonical opening form in core.protocol (see module note).
_OPENING_HINT = "[MSG]"


class Intake:
    """Feeds one source into one deliver callable. No I/O, no clock."""

    def __init__(self, source, deliver):
        self._source = source
        self._deliver = deliver
        self._token = None

    def token(self):
        """Read-only view of the adopted token (None before first adoption)."""
        return self._token

    def process(self):
        """One pass over changes(). Returns [{"id","version","disposition"}].

        Adopts the returned next_token only on a clean pass. Raises through
        unexpected exceptions without adopting.
        """
        items, next_token = self._source.changes(self._token)
        results = []
        for item in items:
            results.append(self._disposition(item))
        self._token = next_token
        return results

    def _disposition(self, item):
        item_id = item["id"]
        version = item["version"]
        if not item.get("final"):
            return {"id": item_id, "version": version,
                    "disposition": SKIPPED}
        block = extract_block(item.get("text", ""))
        if block is None:
            if _OPENING_HINT in (item.get("text") or ""):
                return {"id": item_id, "version": version,
                        "disposition": INVALID_MESSAGE}
            return {"id": item_id, "version": version,
                    "disposition": NO_MESSAGE}
        status, _ = self._deliver(block)
        if status == ACCEPTED:
            return {"id": item_id, "version": version,
                    "disposition": "accepted"}
        return {"id": item_id, "version": version, "disposition": "rejected"}
