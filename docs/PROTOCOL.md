# PROTOCOL — official public agent protocol (v0.1)

How two independent agents exchange transportable messages through the
mediator. Delimiters are protocol structure, not decoration.

## Roles

```
Agent A  →  Mediator  →  Agent B
Agent B  →  Mediator  →  Agent A
```

- A **producing agent** creates a message for the other side.
- The **mediator** extracts, gates, delivers and audits it.
- A **receiving agent** consumes it through its own integration.
- Direction is defined by each concrete integration (which slot, which
  endpoints, which source); the block format itself is direction-free.

## Marker

The public canonical form is:

```
[MSG]
message content
[/MSG]
```

- **Opening** `[MSG]` starts the block and **must begin a line**.
- **Closing** `[/MSG]` ends the block and is **required** — a missing close
  means an incomplete message, which is not transported.
- Only the **first** valid block is extracted.
- Content outside the block is **never** automatically transported.
- Quoted examples inside code fences are ignored by the parser.

## Agent instructions

An agent implementation that wants its output transported MUST:

1. Use the marker when it intends to produce a transportable message.
2. Produce a **complete** block, including the closing tag, before
   considering the message ready.
3. Never assume plain text will be transported.
4. Never implement dedupe, gates or settle policies itself — those belong
   to the mediator.
5. Respect the direction defined by its integration (which side it feeds
   and which side it reads).

## Flow example

```
Agent A
  ↓
[MSG]
Please inspect the failing test and report the root cause.
[/MSG]
  ↓
Mediator (extract → gate → deliver → audit)
  ↓
Agent B
```

Reverse direction works identically:

```
Agent B
  ↓
[MSG]
Root cause: missing await on the database call, fixed in patch 3.
[/MSG]
  ↓
Mediator (extract → gate → deliver → audit)
  ↓
Agent A
```

## Security and protocol notes

- Delimiters are structure: unmarked content is not a message, and an
  unclosed block is incomplete by definition.
- Dedupe, gates, safety fuses and audit are the mediator's
  responsibilities; agents must not duplicate or bypass them.
- This public protocol is deliberately simpler than the private protocol it
  was generalized from: one canonical form, no directional tags, no
  compatibility spellings, no environment-specific markers.
