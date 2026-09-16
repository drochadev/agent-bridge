"""Behavior tests for core.envelope.validate (public contract only)."""
import unittest

from core.envelope import MAX_TEXT_LEN, MAX_TEXTS, ValidationError, validate


class EnvelopeTest(unittest.TestCase):
    def test_minimal_valid_envelope(self):
        out = validate({"generating": False, "finished": True,
                        "texts": ["answer"]})
        self.assertEqual(out, {"generating": False, "finished": True,
                               "texts": ["answer"]})

    def test_optional_flags_default_false(self):
        out = validate({"texts": []})
        self.assertEqual(out, {"generating": False, "finished": False,
                               "texts": []})

    def test_valid_with_optional_and_unknown_fields(self):
        out = validate({"generating": True, "finished": False,
                        "texts": ["part"], "source": "x", "v": 3})
        self.assertEqual(out, {"generating": True, "finished": False,
                               "texts": ["part"]})

    def test_unknown_fields_ignored_not_leaked(self):
        out = validate({"generating": False, "finished": True,
                        "texts": ["a"], "composer": {}, "human": {},
                        "ext_v": "1", "url": "https://x"})
        self.assertEqual(set(out), {"generating", "finished", "texts"})

    def test_generating_not_boolean(self):
        for bad in (1, "yes", None, [True]):
            with self.assertRaises(ValidationError):
                validate({"generating": bad, "texts": []})

    def test_finished_not_boolean(self):
        for bad in (0, "no", None):
            with self.assertRaises(ValidationError):
                validate({"finished": bad, "texts": []})

    def test_texts_not_a_list(self):
        for bad in ("answer", {"t": 1}, None, 42):
            with self.assertRaises(ValidationError):
                validate({"texts": bad})

    def test_texts_item_not_string(self):
        for bad in (["ok", 7], [None], [["nested"]], [{"t": 1}]):
            with self.assertRaises(ValidationError):
                validate({"texts": bad})

    def test_empty_envelope(self):
        with self.assertRaises(ValidationError):
            validate({})

    def test_envelope_not_a_mapping(self):
        for bad in (None, "text", [("texts", [])], 42, {"a", "b"}):
            with self.assertRaises(ValidationError):
                validate(bad)

    def test_texts_above_limit(self):
        with self.assertRaises(ValidationError):
            validate({"texts": ["x"] * (MAX_TEXTS + 1)})
        ok = validate({"texts": ["x"] * MAX_TEXTS})
        self.assertEqual(len(ok["texts"]), MAX_TEXTS)

    def test_text_above_length_limit(self):
        with self.assertRaises(ValidationError):
            validate({"texts": ["x" * (MAX_TEXT_LEN + 1)]})
        ok = validate({"texts": ["x" * MAX_TEXT_LEN]})
        self.assertEqual(len(ok["texts"][0]), MAX_TEXT_LEN)

    def test_error_messages_are_generic(self):
        try:
            validate({"texts": [object()]})
        except ValidationError as exc:
            self.assertNotIn("object", str(exc))
            self.assertLess(len(str(exc)), 80)
        else:
            self.fail("should have raised")

    def test_output_is_detached_copy(self):
        src = ["a"]
        out = validate({"texts": src})
        out["texts"].append("b")
        self.assertEqual(src, ["a"])


if __name__ == "__main__":
    unittest.main()
