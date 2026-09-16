# AGENTS.md — working agreement for coding agents

## Goal

A local, controlled bridge between **ChatGPT** (rich user/project context,
coordinating intelligence) and **OpenCode** (local coding agent with
repository, filesystem and tool access). One new message → one immediate
attempt → delivered or dropped. No queues, no retries, no background ticks.

Independent project. **Not affiliated with or endorsed by OpenAI or the
OpenCode maintainers.** Product names appear only descriptively
("works with …"), never in our own name, branding, or claims.

## Architecture (read `docs/ARCHITECTURE.md` + `docs/PROTOCOL.md` first)

- `core/` — pure rules, stdlib only, no I/O: `delivery` (put/take/settle
  slot), `gate`/`state`/`fuses`/`lifecycle`/`driver` (operations),
  `protocol` (`[MSG]…[/MSG]`, ids, hashes), `policy` (`attempt_once`,
  `take_attempt`), `source`/`intake`/`watcher` (agent→Web intake),
  `envelope`/`stability`/`activity` (observation side), `audit`/`transport`
  (protocols only). **`core` never imports from `adapters/`.**
- `adapters/` — real integrations: `http_slot` + `http_observe` (localhost
  JSON), `observe` (envelope → finished text), `subprocess_injector` +
  `stdout_hash_ack` (local reference transports), `opencode/` (run injector
  + read-only session source), `chatgpt/` (DOM observation mechanism +
  explicit selector config).
- `extension/` — MV3 browser companion (observe → POST, poll → composer →
  DOM proof → confirm). Text-only payloads, never executed.
- No panel yet: state is inspected via tests/logs; do not invent one
  without an order.

## Boundaries that must hold

- Transport failures settle as drops; proofs come only from `Prover`s.
- Audit sinks never break delivery; bodies stay out of audit events.
- Tokens mark processing position; partial source items stay eligible.
- `take()`→`None` means empty OR gate-dropped (audit distinguishes).
- Clocks are always explicit parameters (`now_ms`); no hidden `time()`.
- No shell anywhere (`shell=False`, argv lists); no CORS/auth (localhost
  is the trust perimeter — never expose these servers).

## Environment-dependent parts

- `adapters/opencode/session_source.py` reads OpenCode's **internal**
  SQLite store (verified on v1.18.31). Re-verify table/JSON shapes on every
  OpenCode upgrade; pin the version in your change notes.
- `adapters/chatgpt/selectors.js` + `extension/` DOM knowledge track the
  live ChatGPT Web DOM, which is not a stable API. Update selectors, never
  the mechanism, when the product changes.
- `opencode run` semantics (argv message, `--dir/--model/--session`) were
  read from the installed CLI; re-check `opencode run --help` on upgrade.

## Adapting (other OS / versions)

1. Keep `core/` untouched; add or adjust an `adapters/<product>/` package.
2. New transports implement `Injector`/`Prover` protocols only.
3. New sources implement `Source.changes(token)` honoring the versioning
   guarantee (every content mutation → new observable position).
4. Browser targets get an `extension/`-style companion, never core changes.

## Validating changes

```bash
python3 -m unittest discover -s tests        # must stay fully green
node --test tests/chatgpt/observer.test.mjs tests/extension/content.test.cjs
```

Real smokes (local servers, real binaries, loaded extension) are manual,
separate from the suite, and never required for it to pass.

## Do NOT

- Commit, push, rename, or touch remotes without an explicit order.
- Add secrets, credentials, personal data, private paths, or chat contents.
- Add retries, schedulers, daemons, persistence, auth, or packaging deps
  without an order.
- Copy private-mediator specifics (names, tags, window automation, chat
  schemas, databases) into this repo.
- Claim production readiness, affiliation, or external compatibility the
  tests do not demonstrate.
