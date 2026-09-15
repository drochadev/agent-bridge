# ARCHITECTURE — AI Agent Mediator (public core v0.1)

One-shot delivery: one new message → one immediate attempt → delivered or
dropped. No queues, no retries, no background ticks.

## Responsibilities

- `core/delivery.py` — `OneShotDelivery`: single pending slot. `put()` validates
  (non-empty, deduplicated, gate open) and holds one item, overwriting any
  previous one (audited as `superseded`). `take()` collects once, rechecking the
  gate. `settle(item_id, outcome)` closes the attempt — but only for the item
  returned by the last `take()` and not yet settled; anything else is rejected
  without side effects. Knows nothing about transport.
- `core/gate.py` — `Gate` contract (`is_open() -> (bool, reason)`) + `ManualGate`.
  Checked at `put` AND `take` (decided, tested).
- `core/audit.py` — `AuditSink` contract + `MemoryAuditSink` / `NullAuditSink`.
  Sink failures never break delivery.
- `core/transport.py` — `Injector` (success = no raise; return ignored) and
  `Prover` (truthy = proven) protocols. No concrete implementations yet.
- `core/policy.py` — `attempt_once(delivery, text, inject, prove)`: convenience
  policy wiring put → take → inject → prove. A policy, not the abstraction.
- `core/activity.py` — pure session-activity classifier:
  `classify(snapshot, *, now_ms, fresh_s, residual_min_s)` →
  `waiting | running | completed` with a generic reason. Turn-scoped
  (pre-turn running is stale), freshness covers text-only output, old running
  with an idle session is residual (ignored, reported). No I/O, no clock
  inside, input never mutated.
- `adapters/` — reserved for real-world integrations (subprocess, HTTP, files).
  Empty until a use case needs one. `core` never imports from `adapters`.

## Flow

```
put(text) → [empty? duplicate? gate?] → ACCEPTED id | DROPPED reason
take()    → [empty? gate?] → item (once) | None
settle(id, outcome) → DELIVERED | DROPPED | rejected (wrong/double/unknown)
attempt_once = put → take → inject! → prove? → settle(...)
                                          (any failure settles DROPPED)
```

Events: `accepted / delivered / dropped / superseded`.
NOT thread-safe in this version.
