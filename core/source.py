"""Source contract: observable items with processing-position tokens.

A source NEVER requires the consumer to advance past what it has seen: the
token represents processing position, and the consumer adopts the returned
next_token only when it chooses to. A non-final item therefore stays eligible
across calls — each update carries a newer sequence number, so partial content
can evolve (final=False -> ... -> final=True) without ever being lost.

Item (plain dict): {"id": str, "version": int, "final": bool, "text": str}.
  "version" rises monotonically per id; "final" marks content the consumer
  may treat as complete. Tokens are opaque: pass back what you received
  (None starts from the beginning); invalid tokens raise ValueError.

Source guarantee (required): every content mutation of an item MUST produce
a new observable position/version. Without this, a consumer cannot safely
adopt the token after observing a partial version, and partial content can
be lost. Sources that mutate content invisibly violate this contract; the
intake layer does not work around violating sources.
"""
from typing import Any, Dict, List, Protocol, Tuple, runtime_checkable


@runtime_checkable
class Source(Protocol):
    """Minimum contract."""

    def changes(self, since_token) -> Tuple[List[Dict[str, Any]], Any]:
        ...


class ManualSource:
    """In-memory source for tests and demos. No clock, no I/O.

    upsert() assigns a per-id version and a global sequence number; changes()
    returns the latest state of every id touched after the token, ordered by
    sequence, with next_token covering exactly what was returned.
    """

    def __init__(self):
        self._items = {}  # id -> {version, final, text, seq}
        self._seq = 0

    def upsert(self, item_id, text, final=False):
        """Insert or update one item. Returns its version."""
        if not isinstance(item_id, str) or not item_id:
            raise ValueError("id must be a non-empty string")
        if not isinstance(text, str):
            raise ValueError("text must be a string")
        current = self._items.get(item_id)
        version = (current["version"] + 1) if current else 1
        self._seq += 1
        self._items[item_id] = {"version": version, "final": bool(final),
                                "text": text, "seq": self._seq}
        return version

    def changes(self, since_token=None):
        """Return ([item...], next_token). Items carry id/version/final/text
        (never the internal sequence number)."""
        if since_token is not None and (
                not isinstance(since_token, int) or isinstance(since_token, bool)
                or since_token < 0):
            raise ValueError("invalid token")
        base = since_token if since_token is not None else 0
        fresh = sorted(((item_id, rec) for item_id, rec in self._items.items()
                        if rec["seq"] > base),
                       key=lambda pair: pair[1]["seq"])
        items = [{"id": item_id, "version": rec["version"],
                  "final": rec["final"], "text": rec["text"]}
                 for item_id, rec in fresh]
        next_token = fresh[-1][1]["seq"] if fresh else base
        return items, next_token
