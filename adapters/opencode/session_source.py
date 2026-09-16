"""OpenCode session source: read-only Source over a session database.

Tested against opencode v1.18.31's on-disk SQLite store. That store is an
INTERNAL implementation detail of OpenCode, not a public API: this adapter
depends on observed table/column/JSON shapes (session/message/part,
time_created/time_updated, data.role, data.type, step-finish marker) and may
break on any OpenCode upgrade. Pin and re-verify the OpenCode version when
upgrading.

Mapping (documented, no invented finality):
  id      = assistant message id (stable across in-place updates)
  version = per-id observation counter (rises on every detected change)
  final   = True iff the message owns a step-finish part (structural,
            observed: completed turns have one, the live turn does not)
  text    = text parts concatenated in time_created order ("\\n"-joined)

Change detection is snapshot-based ((max update time, text) per message), so
in-place rewrites are observed without any clock: versions and sequence
numbers come from adapter counters only. Only role "assistant" is surfaced
(configurable); user turns never become items.
"""
import json
import os
import sqlite3


class SessionSource:
    """Read-only. db_path + session_id required (fail-closed, explicit)."""

    def __init__(self, db_path, session_id, roles=("assistant",)):
        if not isinstance(db_path, str) or not db_path:
            raise ValueError("db_path must be a non-empty string")
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"session database not found: {db_path}")
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("session_id must be a non-empty string")
        self._db_path = db_path
        self._session_id = session_id
        self._roles = tuple(roles)
        self._known = {}  # id -> (max_updated, text, version)
        self._seq = 0
        self._versions = {}

    def _connect(self):
        return sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True)

    @staticmethod
    def _load_json(raw):
        try:
            data = json.loads(raw or "{}")
        except (ValueError, TypeError):
            return None
        return data if isinstance(data, dict) else None

    def _snapshot(self):
        conn = self._connect()
        try:
            messages = conn.execute(
                "SELECT id, time_updated, data FROM message"
                " WHERE session_id = ?", (self._session_id,)).fetchall()
            parts = conn.execute(
                "SELECT message_id, time_created, time_updated, data"
                " FROM part WHERE session_id = ?"
                " ORDER BY time_created", (self._session_id,)).fetchall()
        finally:
            conn.close()
        by_message = {}
        for mid, created, updated, raw in parts:
            data = self._load_json(raw)
            if data is None:
                continue  # incomplete/corrupt part: skip, never fail
            by_message.setdefault(mid, []).append((created, updated, data))
        snapshots = {}
        for mid, updated, raw in messages:
            data = self._load_json(raw)
            if data is None or data.get("role") not in self._roles:
                continue
            texts, finish, newest = [], False, updated or 0
            for created, pupd, pdata in by_message.get(mid, []):
                newest = max(newest, pupd or 0)
                ptype = pdata.get("type")
                if ptype == "step-finish":
                    finish = True
                elif ptype == "text":
                    text = pdata.get("text")
                    if isinstance(text, str):
                        texts.append(text)
            snapshots[mid] = (newest, "\n".join(texts), finish)
        return snapshots

    def changes(self, since_token=None):
        """Return ([{id,version,final,text}], next_token). Read-only."""
        if since_token is not None and (
                not isinstance(since_token, int)
                or isinstance(since_token, bool) or since_token < 0):
            raise ValueError("invalid token")
        base = since_token if since_token is not None else 0
        snapshots = self._snapshot()
        fresh = []
        for mid in sorted(snapshots):
            newest, text, finish = snapshots[mid]
            known = self._known.get(mid)
            if known is not None and known[:2] == (newest, text):
                continue  # unchanged since last observation
            version = self._versions.get(mid, 0) + 1
            self._versions[mid] = version
            self._known[mid] = (newest, text)
            self._seq += 1
            if self._seq > base:
                fresh.append((self._seq,
                              {"id": mid, "version": version,
                               "final": finish, "text": text}))
        fresh.sort(key=lambda pair: pair[0])
        items = [item for _, item in fresh]
        next_token = fresh[-1][0] if fresh else base
        return items, next_token
