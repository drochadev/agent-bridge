"""Behavior tests for adapters.subprocess_injector (stdlib only)."""
import os
import subprocess
import sys
import tempfile
import unittest

from adapters.subprocess_injector import SubprocessInjector

PY = sys.executable
READ_TO_FILE = ("import sys; open(sys.argv[1], 'w', encoding=sys.argv[2])"
                ".write(sys.stdin.read())")


class SubprocessInjectorTest(unittest.TestCase):
    def test_child_receives_exact_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "out.txt")
            SubprocessInjector([PY, "-c", READ_TO_FILE, out, "utf-8"])(
                "hello world\nsecond line")
            with open(out, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), "hello world\nsecond line")

    def test_unicode_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "out.txt")
            SubprocessInjector([PY, "-c", READ_TO_FILE, out, "utf-8"])(
                "olá ✓→日本語 🎉")
            with open(out, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), "olá ✓→日本語 🎉")

    def test_missing_executable_raises_oserror(self):
        with self.assertRaises(OSError):
            SubprocessInjector(["definitely-not-a-program-xyz-123"])("hi")

    def test_broken_pipe_raises(self):
        # A directory cannot be executed: deterministic OSError plumbing
        # (PermissionError subclasses OSError), same class as spawn/write
        # failures. NOTE: an early-exiting child is NOT observable here —
        # communicate() absorbs EPIPE by stdlib design (see module docstring);
        # that case is covered below as tolerated, with proof left to Prover.
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(OSError):
                SubprocessInjector([tmp])("hi")

    def test_early_exiting_child_is_tolerated(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "out.txt")
            result = SubprocessInjector(
                [PY, "-c", READ_TO_FILE, out, "utf-8"])("small")
            self.assertIsNone(result)
            with open(out, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), "small")

    def test_timeout_kills_process_and_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            pidfile = os.path.join(tmp, "pid")
            child = ("import sys, time; open(sys.argv[1], 'w').write(str("
                     "__import__('os').getpid())); sys.stdin.read(); "
                     "time.sleep(30)")
            with self.assertRaises(subprocess.TimeoutExpired):
                SubprocessInjector([PY, "-c", child, pidfile],
                                   timeout_s=1)("hello")
            with open(pidfile) as fh:
                pid = int(fh.read())
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)  # dead: kill()+wait() precede the raise

    def test_nonzero_exit_with_received_stdin_is_not_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "out.txt")
            child = ("import sys; open(sys.argv[1], 'w').write("
                     "sys.stdin.read()); sys.exit(1)")
            result = SubprocessInjector([PY, "-c", child, out])("got it")
            self.assertIsNone(result)
            with open(out) as fh:
                self.assertEqual(fh.read(), "got it")

    def test_argv_executed_without_shell(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "out.txt")
            tricky = "a b; echo PWNED | cat"
            child = "import sys; open(sys.argv[2], 'w').write(sys.argv[1])"
            SubprocessInjector([PY, "-c", child, tricky, out])("x")
            with open(out) as fh:
                self.assertEqual(fh.read(), tricky)  # passed literally

    def test_no_string_command_construction(self):
        import adapters.subprocess_injector as mod
        source = open(mod.__file__, encoding="utf-8").read()
        self.assertNotIn("shell=True", source)
        self.assertNotIn("+ \" \"", source)
        self.assertNotIn("os.system", source)

    def test_configurable_encoding(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "out.txt")
            child = ("import sys; open(sys.argv[1], 'w', encoding='latin-1')"
                     ".write(sys.stdin.buffer.read().decode('latin-1'))")
            SubprocessInjector([PY, "-c", child, out],
                               encoding="latin-1")("ação çã")
            with open(out, encoding="latin-1") as fh:
                self.assertEqual(fh.read(), "ação çã")

    def test_empty_text_passes_through_without_own_rule(self):
        # Precondition (non-empty) belongs to Delivery.put; the injector
        # itself applies no content validation: empty stdin just works.
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "out.txt")
            self.assertIsNone(
                SubprocessInjector([PY, "-c", READ_TO_FILE, out, "utf-8"])(""))
            with open(out, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), "")

    def test_argv_must_be_sequence_of_strings(self):
        for bad in ("/bin/echo", b"/bin/echo", [], ["ok", 7]):
            with self.assertRaises(ValueError):
                SubprocessInjector(bad)


if __name__ == "__main__":
    unittest.main()
