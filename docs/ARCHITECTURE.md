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
- `core/fuses.py` — safety fuses over a delivery **history** callable
  (`Fuses(history=...)`, records `{at_ms, hash, confirmed}`). This is NOT the
  content `Source` from `core/source.py`: fuses read delivery outcomes, never
  content items; the two contracts are intentionally different shapes.
- `core/audit.py` — `AuditSink` contract + `MemoryAuditSink` / `NullAuditSink`.
  Sink failures never break delivery.
- `core/transport.py` — `Injector` (success = no raise; return ignored) and
  `Prover` (truthy = proven) protocols. Reference implementations live in
  `adapters/` (`subprocess_injector`, `stdout_hash_ack`).
- `core/protocol.py` — public message surface: `extract_block` (canonical
  `[MSG]…[/MSG]`, line-anchored, first block only, fences ignored),
  `make_id`, `content_hash`, and caller-owned `contains_reserved_marker`.
  Message contract: plain `{id, body, origin}`. Flow:
  input → extract_block → message contract → OneShotDelivery.
- `core/policy.py` — `attempt_once(delivery, text, inject, prove)`: convenience
  policy wiring put → take → inject → prove. A policy, not the abstraction.
- `core/lifecycle.py` — coordination only: `poll(now_ms)` evaluates fuses and
  engages `SAFETY_HOLD` on trip; `gate()` exposes state + last evaluation as a
  `Gate` for `Delivery`. Fuses detect, machine holds, gate exposes, delivery
  applies. Driver calls `poll()` each cycle (explicit clock, no hidden time).
- `core/driver.py` — one explicit cycle: `run_once(now_ms)` advances the
  lifecycle exactly once. No loops, threads, sleep, or I/O; seam for future
  schedulers.
- `core/intake.py` — agent-to-Web intake: `Intake(source, deliver)` +
  `process()->[{id,version,disposition}]` over `skipped/no-message/
  invalid-message/accepted/rejected`. Token adopted only on a clean pass;
  no retry inside.
- `core/flow.py` — Web-to-agent wiring only: `Flow(feed, delivery, inject,
  prove)` + `process(envelope)` → `("idle", None)` without touching delivery,
  or the `attempt_once` result verbatim. No gate/dedupe/settle/audit/retry of
  its own.
- `core/stability.py` — pure generation-cycle detector: successive
  `observe(generating, finished, texts)` emit `{"text"}` exactly once per
  finished response (last non-empty text wins; same response never re-emits).
- `core/source.py` — `Source` contract (`changes(token)->(items,next_token)`,
  items `{id,version,final,text}`) + `ManualSource` (in-memory, no clock).
  Tokens mark processing position; non-final items stay eligible across
  calls, so partial content can evolve to final without loss.
- `core/envelope.py` — border validator: untrusted mapping →
  `{"generating", "finished", "texts"}` or `ValidationError`. Unknown fields
  ignored (never leak); limits `MAX_TEXTS=500`, `MAX_TEXT_LEN=100000`.
- `core/activity.py` — pure session-activity classifier:
  `classify(snapshot, *, now_ms, fresh_s, residual_min_s)` →
  `waiting | running | completed` with a generic reason. Turn-scoped
  (pre-turn running is stale), freshness covers text-only output, old running
  with an idle session is residual (ignored, reported). No I/O, no clock
  inside, input never mutated.
- `adapters/` — real-world integrations. `http_slot` (single global slot)
  is a thin JSON skin over `OneShotDelivery`. `observe` (`ObservationFeed`)
  composes `validate` + `StabilityDetector`: envelope → finished text, with
  no transport and no I/O. `subprocess_injector` (`SubprocessInjector`):
  argv-only stdin delivery, one process per attempt, EPIPE absorbed by
  stdlib (proof stays with Prover). `stdout_hash_ack` (`StdoutHashAck`):
  dual-role injector+prover over one process run — inject captures stdout
  keyed by id, `prove` matches the sent-bytes SHA-256 (use as
  `prove=ack.prove`). HTTP/observation/injection are adapters,
  never core:

```
HTTP adapter  →  OneShotDelivery  →  slot lifecycle
(slot HTTP)      (put/take/settle)   (accepted/taken/settled|rejected)
```

## Flow

```
put(text) → [empty? duplicate? gate?] → ACCEPTED id | DROPPED reason
take()    → [empty? gate?] → item (once) | None
settle(id, outcome) → DELIVERED | DROPPED | rejected (wrong/double/unknown)
attempt_once = put → take → inject! → prove? → settle(...)
                                           (any failure settles DROPPED)
take_attempt = take → inject! → prove? → settle(...)   (empty → ("empty",None))
```

Events: `accepted / delivered / dropped / superseded`.
NOT thread-safe in this version.
