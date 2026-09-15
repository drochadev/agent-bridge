"""Behavior tests for core.protocol (public contract only)."""
import re
import unittest

from core.protocol import (
    contains_reserved_marker,
    content_hash,
    extract_block,
    make_id,
)


class ProtocolTest(unittest.TestCase):
    def test_valid_block(self):
        self.assertEqual(
            extract_block("[MSG]\nhello\n[/MSG]"), "hello")

    def test_no_block(self):
        self.assertIsNone(extract_block("just plain text"))
        self.assertIsNone(extract_block(""))
        self.assertIsNone(extract_block(None))

    def test_text_before_and_after_ignored(self):
        text = "before\n[MSG]\nbody\n[/MSG]\nafter"
        self.assertEqual(extract_block(text), "body")

    def test_only_first_block_travels(self):
        text = "[MSG]\nfirst\n[/MSG]\n[MSG]\nsecond\n[/MSG]"
        self.assertEqual(extract_block(text), "first")

    def test_unclosed_block_produces_nothing(self):
        self.assertIsNone(extract_block("x\n[MSG]\nrest here"))

    def test_code_fence_ignored(self):
        text = "example:\n```\n[MSG]\nnot a block\n[/MSG]\n```\n[MSG]\nreal\n[/MSG]"
        self.assertEqual(extract_block(text), "real")

    def test_opening_must_start_a_line(self):
        self.assertIsNone(extract_block("prefix [MSG]\nbody\n[/MSG]"))

    def test_whitespace_stripped(self):
        self.assertEqual(extract_block("[MSG]\n   spaced   \n[/MSG]"), "spaced")
        self.assertIsNone(extract_block("[MSG]\n   \n[/MSG]"))

    def test_ids_unique_and_shaped(self):
        ids = {make_id() for _ in range(200)}
        self.assertEqual(len(ids), 200)
        for i in ids:
            self.assertRegex(i, r"^msg_[0-9a-f]{12}$")

    def test_hash_deterministic(self):
        self.assertEqual(content_hash("abc"), content_hash("abc"))
        self.assertEqual(len(content_hash("abc")), 64)
        self.assertRegex(content_hash("abc"), r"^[0-9a-f]{64}$")

    def test_hash_differs_per_body(self):
        self.assertNotEqual(content_hash("a"), content_hash("b"))
        self.assertNotEqual(content_hash("a"), content_hash("a "))

    def test_reserved_marker_configurable(self):
        self.assertTrue(contains_reserved_marker("has X inside", ("X",)))
        self.assertTrue(contains_reserved_marker("a", ("a", "b")))
        self.assertFalse(contains_reserved_marker("clean", ("X", "Y")))

    def test_reserved_marker_empty_by_default(self):
        self.assertFalse(contains_reserved_marker("anything at all"))
        self.assertFalse(contains_reserved_marker("anything", ()))

    def test_no_private_names(self):
        import core.protocol as proto
        source = open(proto.__file__, encoding="utf-8").read()
        for forbidden in ("Pedro", "João", "Joao", "Diogo", "PEDRO",
                          "JOÃO", "openCode", "chatgpt", "xdotool"):
            self.assertNotIn(forbidden, source)
        self.assertNotIn("re.IGNORECASE", source)  # canonical form only


if __name__ == "__main__":
    unittest.main()
