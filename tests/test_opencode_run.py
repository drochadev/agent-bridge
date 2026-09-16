"""Behavior tests for adapters.opencode.run (hermetic fakes only)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

from adapters.opencode.run import OpencodeRunInjector

PY = sys.executable
FAKE_SCRIPT = (
    "#!/usr/bin/env python3\n"
    "import sys, json, time\n"
    "args = sys.argv[1:]\n"
    "assert args[0] == 'run', args\n"
    "rest = args[1:]\n"
    "if '--record' in rest:\n"
    "    i = rest.index('--record')\n"
    "    open(rest[i + 1], 'w').write(json.dumps(rest))\n"
    "elif '--sleep' in rest:\n"
    "    time.sleep(30)\n"
    "else:\n"
    "    raise SystemExit('unknown fake mode')\n"
)


class OpencodeRunInjectorTest(unittest.TestCase):
    def fake(self, tmp, *mode_args, **kwargs):
        script = os.path.join(tmp, "fake-opencode")
        with open(script, "w") as fh:
            fh.write(FAKE_SCRIPT)
        os.chmod(script, 0o755)
        out = os.path.join(tmp, "argv.json")
        inj = OpencodeRunInjector(script,
                                  extra_args=list(mode_args) + [out],
                                  **kwargs)
        return inj, out

    def read_argv(self, out):
        with open(out) as fh:
            return json.load(fh)

    def test_message_as_single_argv_element(self):
        with tempfile.TemporaryDirectory() as tmp:
            inj, out = self.fake(tmp, "--record")
            self.assertIsNone(inj({"id": "m1", "body": "do the thing"}))
            argv = self.read_argv(out)
            self.assertEqual(argv[-1], "do the thing")

    def test_project_dir_model_session_flags(self):
        with tempfile.TemporaryDirectory() as tmp:
            inj, out = self.fake(tmp, "--record", project_dir="/proj",
                                 model="prov/model", session="s123")
            inj({"id": "m1", "body": "hi"})
            argv = self.read_argv(out)
            for flag in ("--dir", "/proj", "--model", "prov/model",
                         "--session", "s123"):
                self.assertIn(flag, argv)

    def test_no_shell_metacharacters_interpreted(self):
        with tempfile.TemporaryDirectory() as tmp:
            inj, out = self.fake(tmp, "--record")
            tricky = "a; rm -rf / | $(evil) `back`"
            inj({"id": "m1", "body": tricky})
            self.assertEqual(self.read_argv(out)[-1], tricky)

    def test_missing_binary_raises_oserror(self):
        inj = OpencodeRunInjector("definitely-not-opencode-xyz")
        with self.assertRaises(OSError):
            inj({"id": "m1", "body": "hi"})

    def test_timeout_kills_and_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            inj, out = self.fake(tmp, "--sleep", timeout_s=1)
            with self.assertRaises(subprocess.TimeoutExpired):
                inj({"id": "m1", "body": "hi"})

    def test_argv_for_inspection(self):
        inj = OpencodeRunInjector("opencode", project_dir="/p")
        argv = inj.argv_for("hello")
        self.assertEqual(argv, ["opencode", "run", "--dir", "/p", "hello"])

    def test_invalid_argv0_rejected(self):
        for bad in ("", b"opencode", 123, None):
            with self.assertRaises(ValueError):
                OpencodeRunInjector(bad)

    def test_unicode_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            inj, out = self.fake(tmp, "--record")
            inj({"id": "m1", "body": "olá ✓"})
            self.assertEqual(self.read_argv(out)[-1], "olá ✓")

    def test_no_shell_in_source(self):
        import adapters.opencode.run as mod
        source = open(mod.__file__, encoding="utf-8").read()
        self.assertNotIn("shell=True", source)
        self.assertNotIn("os.system", source)


if __name__ == "__main__":
    unittest.main()
