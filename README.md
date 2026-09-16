# AI Agent Mediator

A public, generalized implementation of one-shot delivery between two
independent agents through a mediator. One new message → one immediate
attempt → delivered or dropped. No queues, no retries, no background ticks.

This is **not** a production framework, SaaS, or deployment-ready distributed
system. It is a small, readable codebase (stdlib-only Python) extracted and
generalized from a real working mediator, with 217 tests covering its
contracts and deterministic behavior — not compatibility with any external
environment. Concurrency, authentication, distributed deployment and similar
concerns are explicitly out of v0.1.

## The problem it solves

Two agents (for example, a web-side assistant and a local coding agent) need
to exchange messages through an unreliable middle: processes restart,
responses stream in partially, networks fail, humans pause the system. The
mediator gives both directions the same guarantees: every message gets
exactly one immediate attempt; partial content is never silently lost by the
consumer contract; delivery is never presumed without proof; runaway loops
trip safety fuses instead of flooding anyone.

## The concept

```
Agent A  →  Mediator  →  Agent B
Agent B  →  Mediator  →  Agent A
```

Each agent only ever talks to the mediator, never directly to the other
agent. The mediator holds at most one pending message per direction, checks
operational gates before moving anything, and records every outcome in an
audit sink.

## Architecture overview

- `core/delivery.py` — single pending slot: `put` / `take` (take-once) /
  `settle` (single validated close).
- `core/gate.py`, `core/state.py`, `core/fuses.py`, `core/lifecycle.py`,
  `core/driver.py` — operational gates, state machine, safety fuses and the
  explicit per-cycle driver that wires them together.
- `core/protocol.py` — canonical `[MSG]…[/MSG]` block extraction, ids, hashes.
- `core/policy.py` — `attempt_once` (push) and `take_attempt` (pull) policies.
- `core/source.py`, `core/intake.py` — observable sources with
  processing-position tokens (partial content stays eligible).
- `core/envelope.py`, `core/stability.py`, `core/activity.py` — source
  envelope validation, generation-cycle detection, activity classification.
- `core/audit.py`, `core/transport.py` — audit-sink and injector/prover
  protocols (interfaces, not implementations).
- `adapters/` — real-world integrations (never imported by `core`):
  `http_slot` (localhost JSON slot), `observe` (envelope → finished text),
  `subprocess_injector` and `stdout_hash_ack` (local reference mechanisms).

See `docs/ARCHITECTURE.md` for responsibilities and `docs/PROTOCOL.md` for
the official agent protocol.

## Flows

**Source → agent** (e.g. web side to local agent): source envelope →
validate → stability detection → finished text → `attempt_once` (put → take
→ inject → prove → settle), with the lifecycle gate enforced.

**Agent → source** (e.g. local agent to web side): observable source →
`Intake` (extract final blocks, `put`) → external consumer collects via
`take` → confirms via `settle`. Non-final content stays eligible through
versioned source tokens.

## Key properties

- **One-shot delivery** — one attempt per message; failure is an honest
  `dropped` with a reason, never a silent retry.
- **Take-once** — collection invalidates the slot; a second take gets nothing.
- **Dedupe** — sha256 content memory (bounded, FIFO) rejects repeats.
- **Gates** — checked at `put` AND `take`; closed gates drop with reasons.
- **Safety fuses** — turn/rate/repetition limits over confirmed deliveries,
  engaging `SAFETY_HOLD` through the lifecycle.
- **Lifecycle** — explicit state machine (`stopped/open/paused/safety_hold`)
  advanced by an explicit per-cycle driver; no hidden clocks.
- **Proof of delivery** — success requires independent evidence (a `Prover`),
  never the injector's return value.
- **Source/intake** — versioned sources; partial items remain eligible until
  final; token adoption only on clean passes.

## Repository layout

```
core/       generic rules (no I/O, stdlib only)
adapters/   real integrations (HTTP, observation, subprocesses)
tests/      contract tests, stdlib unittest only
docs/       ARCHITECTURE.md, PROTOCOL.md
```

## Quickstart

Requires Python 3.8+ (tested on 3.12), no dependencies:

```bash
cd ai-agent-mediator-public
python3 -m unittest discover -s tests
```

All 217 tests should pass in a few seconds.

## Conceptual example

```python
from core.delivery import OneShotDelivery
from core.gate import ManualGate
from core.audit import MemoryAuditSink
from core.policy import attempt_once

delivery = OneShotDelivery(gate=ManualGate(), audit=MemoryAuditSink())
status, detail = attempt_once(
    delivery, "hello",
    inject=lambda item: print("inject:", item["body"]),
    prove=lambda item: True,
)
print(status, detail)  # delivered <id>
```

## Project status and limitations

- v0.1 scope: in-memory core + localhost/reference adapters. No persistence,
  no authentication, no multi-slot routing, no scheduler/daemon, no browser
  or agent-specific integrations.
- `SubprocessInjector` and `StdoutHashAck` are **local reference mechanisms**,
  not production transports; HTTP is **localhost-oriented**; some adapters
  are integration examples.
- Tests cover contracts and deterministic behavior, not external compatibility.

## Deliberate differences from the private mediator

This codebase generalizes a real private mediator and is not a 1:1 copy:
agent names and directional tags are replaced by the generic `[MSG]` block;
private infrastructure (window automation, browser extension, chat-service
schemas, local databases, operator tooling) is replaced by protocols and
reference adapters; the audit emits `delivered`/`superseded` events the
private log lacks; safety thresholds are parameters, not hard-coded values.
Behavioral parity is documented per component, not assumed globally.
