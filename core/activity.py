"""Activity classification: is the agent idle, working, or done?

Pure function (no I/O, no clock inside, no globals). Faithful extraction of
the proven verdict logic: turn scoping, freshness for text-only output, and
residual detection. Thresholds are parameters, not globals.

Input snapshot (plain dicts, never mutated):
  roles:   [{id, role, created}]               # "user" | "assistant"
  running: [{message_id, tool, created}]       # units still marked running
  n_parts: int                                 # total unit count (for reasons)
  session: {time_updated} | None

Verdicts: WAITING (needs input) | RUNNING (working now) | COMPLETED (idle).
Reasons are generic: no names, no paths, no ids.
"""
WAITING = "waiting"
RUNNING = "running"
COMPLETED = "completed"


def classify(snapshot, *, now_ms, fresh_s=15, residual_min_s=900):
    """Classify current activity. now_ms is required (explicit clock)."""
    roles = snapshot.get("roles", [])
    running = snapshot.get("running", [])
    if not roles:
        return WAITING, "empty session"
    last = roles[-1]
    if last.get("role") == "user":
        if running:
            return (WAITING,
                    f"last message is from user; {len(running)} "
                    "running outside turn (stale)")
        return WAITING, "last message is from user"
    msg_created = {r["id"]: r.get("created", 0)
                   for r in roles if "id" in r}
    user_times = [r.get("created", 0) for r in roles
                  if r.get("role") == "user"]
    last_user = max(user_times) if user_times else None
    current, stale = [], []
    for run in running:
        mc = msg_created.get(run.get("message_id"))
        if last_user is None or mc is None or mc >= last_user:
            current.append(run)
        else:
            stale.append(run)
    sess_upd = (snapshot.get("session") or {}).get("time_updated") or 0
    limite = now_ms - residual_min_s * 1000
    live, residual = [], []
    for run in current:
        if (run.get("created") or now_ms) < limite and sess_upd < limite:
            residual.append(run)
        else:
            live.append(run)
    stale_note = f"; {len(stale)} stale ignored" if stale else ""
    residual_note = f"; {len(residual)} residual ignored" if residual else ""
    if live:
        tools = ",".join(sorted({r.get("tool", "?") for r in live}))
        return (RUNNING,
                f"{len(live)} running part(s) in current turn "
                f"({tools}){stale_note}{residual_note}")
    if sess_upd >= now_ms - fresh_s * 1000:
        why = (f"session active {(now_ms - sess_upd) // 1000}s ago "
               "(plain text?)")
        if residual:
            why += residual_note
        return RUNNING, why
    n_parts = snapshot.get("n_parts", 0)
    idle_s = (now_ms - sess_upd) // 1000
    return (COMPLETED,
            f"last message is assistant, {n_parts} parts, "
            f"idle {idle_s}s{stale_note}{residual_note}")
