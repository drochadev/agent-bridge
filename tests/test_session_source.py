"""Behavior tests for adapters.opencode.session_source (fake SQLite only)."""
import hashlib
import json
import os
import sqlite3
import tempfile
import unittest

from adapters.opencode.session_source import SessionSource

SCHEMA = """
CREATE TABLE message(id TEXT, session_id TEXT, time_created INTEGER,
                     time_updated INTEGER, data TEXT);
CREATE TABLE part(id TEXT, message_id TEXT, session_id TEXT,
                  time_created INTEGER, time_updated INTEGER, data TEXT);
"""


def build_db(path, session="sess1", messages=(), parts=()):
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    for mid, created, updated, role in messages:
        conn.execute("INSERT INTO message VALUES (?,?,?, ?, ?)",
                     (mid, session, created, updated,
                      json.dumps({"role": role})))
    for pid, mid, created, updated, ptype, extra in parts:
        data = {"type": ptype}
        data.update(extra)
        conn.execute("INSERT INTO part VALUES (?,?,?,?,?,?)",
                     (pid, mid, session, created, updated,
                      json.dumps(data)))
    conn.commit()
    conn.close()


def text_part(text):
    return ("text", {"text": text})


class SessionSourceTest(unittest.TestCase):
    def make(self, **kwargs):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        db = os.path.join(tmp.name, "fake.db")
        params = {"db_path": db, "session_id": "sess1"}
        params.update(kwargs)
        return db, params

    def checksum(self, db):
        with open(db, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()

    def test_first_read(self):
        db, params = self.make()
        build_db(db, messages=[("m1", 100, 100, "assistant")],
                 parts=[("p1", "m1", 100, 100) + text_part("hi")])
        src = SessionSource(**params)
        items, token = src.changes(None)
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["id"], "m1")
        self.assertEqual(item["version"], 1)
        self.assertFalse(item["final"])
        self.assertEqual(item["text"], "hi")
        self.assertNotIn("seq", item)

    def test_incremental_token(self):
        db, params = self.make()
        build_db(db, messages=[("m1", 100, 100, "assistant")],
                 parts=[("p1", "m1", 100, 100) + text_part("hi")])
        src = SessionSource(**params)
        _, t1 = src.changes(None)
        items, t2 = src.changes(t1)
        self.assertEqual(items, [])
        self.assertEqual(t2, t1)

    def test_new_message(self):
        db, params = self.make()
        build_db(db, messages=[("m1", 100, 100, "assistant")],
                 parts=[("p1", "m1", 100, 100) + text_part("hi")])
        src = SessionSource(**params)
        src.changes(None)
        conn = sqlite3.connect(db)
        conn.execute("INSERT INTO message VALUES (?,?,?,?,?)",
                     ("m2", "sess1", 200, 200,
                      json.dumps({"role": "assistant"})))
        conn.execute("INSERT INTO part VALUES (?,?,?,?,?,?)",
                     ("p2", "m2", "sess1", 200, 200,
                      json.dumps({"type": "text", "text": "yo"})))
        conn.commit()
        conn.close()
        # fresh adapter, same token semantics: new id appears
        src2 = SessionSource(**params)
        items, _ = src2.changes(None)
        self.assertEqual({i["id"] for i in items}, {"m1", "m2"})

    def test_update_same_message_new_version(self):
        db, params = self.make()
        build_db(db, messages=[("m1", 100, 100, "assistant")],
                 parts=[("p1", "m1", 100, 100) + text_part("half")])
        src = SessionSource(**params)
        first, t1 = src.changes(None)
        self.assertFalse(first[0]["final"])
        conn = sqlite3.connect(db)
        conn.execute("UPDATE part SET time_updated=200, data=? WHERE id='p1'",
                     (json.dumps({"type": "text",
                                  "text": "half done"}),))
        conn.execute("INSERT INTO part VALUES (?,?,?,?,?,?)",
                     ("p2", "m1", "sess1", 150, 200,
                      json.dumps({"type": "step-finish"})))
        conn.commit()
        conn.close()
        second, t2 = src.changes(t1)
        self.assertEqual(len(second), 1)
        self.assertEqual(second[0]["version"], 2)
        self.assertTrue(second[0]["final"])
        self.assertIn("half done", second[0]["text"])
        self.assertGreater(t2, t1)

    def test_user_messages_never_surface(self):
        db, params = self.make()
        build_db(db, messages=[("u1", 100, 100, "user")],
                 parts=[("p1", "u1", 100, 100) + text_part("prompt")])
        src = SessionSource(**params)
        items, _ = src.changes(None)
        self.assertEqual(items, [])

    def test_other_sessions_ignored(self):
        db, params = self.make()
        build_db(db, session="sess9",
                 messages=[("m9", 100, 100, "assistant")],
                 parts=[("p9", "m9", 100, 100) + text_part("other")])
        src = SessionSource(**params)  # watches sess1
        items, _ = src.changes(None)
        self.assertEqual(items, [])

    def test_empty_database(self):
        db, params = self.make()
        build_db(db)
        src = SessionSource(**params)
        self.assertEqual(src.changes(None), ([], 0))

    def test_incomplete_data_skipped(self):
        db, params = self.make()
        build_db(db, messages=[("m1", 100, 100, "assistant")],
                 parts=[("p1", "m1", 100, 100) + text_part("ok")])
        conn = sqlite3.connect(db)
        conn.execute("INSERT INTO part VALUES (?,?,?,?,?,?)",
                     ("bad", "m1", "sess1", 101, 101, "{not json"))
        conn.execute("INSERT INTO message VALUES (?,?,?,?,?)",
                     ("m2", "sess1", 102, 102, "nope"))
        conn.commit()
        conn.close()
        src = SessionSource(**params)
        items, _ = src.changes(None)  # never raises on content
        self.assertEqual([i["id"] for i in items], ["m1"])

    def test_missing_database(self):
        with self.assertRaises(FileNotFoundError):
            SessionSource("/nonexistent/dir/fake.db", "sess1")

    def test_invalid_config(self):
        db, params = self.make()
        build_db(db)
        with self.assertRaises(ValueError):
            SessionSource("", "sess1")
        with self.assertRaises(ValueError):
            SessionSource(db, "")
        src = SessionSource(**params)
        with self.assertRaises(ValueError):
            src.changes("forged")
        with self.assertRaises(ValueError):
            src.changes(-1)

    def test_database_never_written(self):
        db, params = self.make()
        build_db(db, messages=[("m1", 100, 100, "assistant")],
                 parts=[("p1", "m1", 100, 100) + text_part("hi")])
        before = self.checksum(db)
        src = SessionSource(**params)
        src.changes(None)
        src.changes(0)
        self.assertEqual(self.checksum(db), before)

    def test_text_parts_concatenated_in_order(self):
        db, params = self.make()
        build_db(db, messages=[("m1", 100, 100, "assistant")],
                 parts=[("p2", "m1", 200, 200) + text_part("second"),
                        ("p1", "m1", 100, 100) + text_part("first")])
        src = SessionSource(**params)
        items, _ = src.changes(None)
        self.assertEqual(items[0]["text"], "first\nsecond")

    def test_no_private_coupling(self):
        import adapters.opencode.session_source as mod
        source = open(mod.__file__, encoding="utf-8").read()
        for forbidden in ("opencode.db", ".local/share", "HOME",
                          "Chrome", "chatgpt", "xdotool"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
