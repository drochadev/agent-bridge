"""One-shot delivery slot: put/take-once with injectable gate and audit.

Public nucleus extracted from observed behavior. Stdlib only.
No SQLite, no HTTP, no X11, no private components. No transport here:
injection and proof live in core.transport / core.policy.

Thread-safety: OneShotDelivery is NOT thread-safe in this version. External
synchronization is required if shared between threads.

Input normalization: put() strips leading/trailing whitespace; the stripped
form is stored, hashed for deduplication, and delivered.
"""
import hashlib
import uuid
from collections import OrderedDict

from core.audit import AuditSink
from core.gate import Gate

ACCEPTED = "accepted"
DROPPED = "dropped"
DELIVERED = "delivered"
SUPERSEDED = "superseded"


def _content_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _new_id():
    return "msg_" + uuid.uuid4().hex[:12]


class OneShotDelivery:
    """Single pending slot. put() accepts at most one message; take() collects once.

    gate:  Gate, checked at put AND take (decided). See core.gate.
    audit: AuditSink. Receives accepted / delivered / dropped / superseded.
           Exceptions raised by the sink are swallowed so observability can
           never break delivery. See core.audit.

    NOT thread-safe (see module note).
    """

    def __init__(self, gate: Gate, audit: AuditSink, seen_limit: int = 32):
        self._gate = gate
        self._audit = audit
        self._seen_limit = seen_limit
        self._seen = OrderedDict()  # digest -> None; FIFO eviction
        self._pending = None
        self._open_attempt = None  # id returned by the last take(), unsettled

    def _emit(self, event, detail=""):
        try:
            self._audit.record(event, detail)
        except Exception:
            pass  # audit must never break delivery

    def _reject(self, reason):
        """Refuse new input without touching existing pending state."""
        self._emit(DROPPED, reason)
        return DROPPED, reason

    def _drop(self, reason):
        """Abort the current attempt and clear pending state."""
        self._pending = None
        self._emit(DROPPED, reason)
        return DROPPED, reason

    def _remember(self, digest):
        self._seen[digest] = None
        while len(self._seen) > self._seen_limit:
            self._seen.popitem(last=False)  # deterministic FIFO eviction

    def put(self, text):
        body = (text or "").strip()
        if not body:
            return self._reject("empty-text")
        digest = _content_hash(body)
        if digest in self._seen:
            return self._reject("duplicate")
        open_, reason = self._gate.is_open()
        if not open_:
            return self._reject(f"gate-closed: {reason}")
        self._remember(digest)
        previous = self._pending
        item = {"id": _new_id(), "body": body}
        self._pending = item  # overwrites previous pending by design
        if previous is not None:
            self._emit(SUPERSEDED, previous["id"])
        self._emit(ACCEPTED, item["id"])
        return ACCEPTED, item["id"]

    def take(self):
        if self._pending is None:
            return None
        open_, reason = self._gate.is_open()
        if not open_:
            self._drop(f"gate-closed-at-take: {reason}")
            return None
        item = self._pending
        self._pending = None
        self._open_attempt = item["id"]
        return item

    def settle(self, item_id, outcome, reason=None):
        """Single attempt-closing operation.

        Only the item returned by the last take() and not yet settled can be
        closed. outcome is "delivered" or "dropped". Anything else — unknown
        item, superseded item, already-settled item, item from another attempt,
        unknown outcome — is rejected with ("rejected", detail) without
        changing any state and without emitting an audit event.
        """
        if outcome not in (DELIVERED, DROPPED):
            return "rejected", f"unknown-outcome: {outcome}"
        if self._open_attempt is None or self._open_attempt != item_id:
            return "rejected", f"not-open-attempt: {item_id}"
        self._open_attempt = None
        if outcome == DELIVERED:
            self._emit(DELIVERED, item_id)
            return DELIVERED, item_id
        detail = reason or item_id
        self._emit(DROPPED, detail)
        return DROPPED, detail
