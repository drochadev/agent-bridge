"""Behavior tests for adapters.stdout_hash_ack (stdlib only)."""
import subprocess
import sys
import unittest

from adapters.stdout_hash_ack import StdoutHashAck
from core.delivery import DELIVERED, DROPPED
from core.policy import attempt_once

PY = sys.executable
PRINT_HASH = ("import sys, hashlib; sys.stdout.write("
              "hashlib.sha256(sys.stdin.buffer.read()).hexdigest())")
PRINT_WRONG = "import sys; sys.stdout.write('0' * 64)"


def item(id_, body="hello"):
    return {"id": id_, "body": body}


class StdoutHashAckTest(unittest.TestCase):
    def test_correct_hash_proves_true(self):
        ack = StdoutHashAck([PY, "-c", PRINT_HASH])
        it = item("m1", "hello")
        self.assertIsNone(ack(it))
        self.assertTrue(ack.prove(it))

    def test_wrong_hash_proves_false(self):
        ack = StdoutHashAck([PY, "-c", PRINT_WRONG])
        it = item("m1", "hello")
        ack(it)
        self.assertFalse(ack.prove(it))

    def test_empty_stdout_proves_false(self):
        ack = StdoutHashAck([PY, "-c", "pass"])
        it = item("m1", "hello")
        ack(it)
        self.assertFalse(ack.prove(it))

    def test_malformed_stdout_proves_false(self):
        ack = StdoutHashAck([PY, "-c", "import sys; sys.stdout.write('hi')"])
        it = item("m1", "hello")
        ack(it)
        self.assertFalse(ack.prove(it))

    def test_unicode_body(self):
        ack = StdoutHashAck([PY, "-c", PRINT_HASH])
        it = item("m1", "olá ✓→日本語")
        ack(it)
        self.assertTrue(ack.prove(it))

    def test_attempts_do_not_share_proof(self):
        ack = StdoutHashAck([PY, "-c", PRINT_HASH])
        ack(item("a", "same body"))
        ack(item("b", "same body"))
        self.assertTrue(ack.prove(item("a", "same body")))
        self.assertTrue(ack.prove(item("b", "same body")))
        self.assertFalse(ack.prove(item("c", "same body")))

    def test_missing_executable(self):
        ack = StdoutHashAck(["definitely-not-a-program-xyz-123"])
        with self.assertRaises(OSError):
            ack(item("m1"))
        self.assertFalse(ack.prove(item("m1")))

    def test_timeout_kills_and_proves_nothing(self):
        child = "import sys, time; sys.stdin.read(); time.sleep(30)"
        ack = StdoutHashAck([PY, "-c", child], timeout_s=1)
        it = item("m1", "hello")
        with self.assertRaises(subprocess.TimeoutExpired):
            ack(it)
        self.assertFalse(ack.prove(it))

    def test_nonzero_exit_with_correct_hash_still_proves(self):
        child = PRINT_HASH + "; import sys; sys.exit(3)"
        ack = StdoutHashAck([PY, "-c", child])
        it = item("m1", "hello")
        self.assertIsNone(ack(it))
        self.assertTrue(ack.prove(it))

    def test_prove_does_no_io_or_wait(self):
        import inspect
        source = inspect.getsource(StdoutHashAck.prove)
        for forbidden in ("Popen", "communicate", "sleep", "wait(",
                          "open(", "socket"):
            self.assertNotIn(forbidden, source)
        ack = StdoutHashAck([PY, "-c", PRINT_HASH])
        it = item("m1", "hi")
        ack(it)
        self.assertTrue(ack.prove(it))  # instant local lookup

    def test_capture_bound_is_fifo(self):
        ack = StdoutHashAck([PY, "-c", PRINT_HASH], max_captures=2)
        ack(item("a", "one"))
        ack(item("b", "two"))
        ack(item("c", "three"))
        self.assertFalse(ack.prove(item("a", "one")))  # evicted
        self.assertTrue(ack.prove(item("b", "two")))
        self.assertTrue(ack.prove(item("c", "three")))

    def test_attempt_once_delivered(self):
        from core.audit import MemoryAuditSink
        from core.delivery import OneShotDelivery
        from core.gate import ManualGate
        ack = StdoutHashAck([PY, "-c", PRINT_HASH])
        audit = MemoryAuditSink()
        delivery = OneShotDelivery(gate=ManualGate(), audit=audit)
        # dual role: inject=ack (__call__), prove=ack.prove (method).
        # Passing the object itself as prove would invoke __call__ again.
        st, detail = attempt_once(delivery, "hello", ack, ack.prove)
        self.assertEqual(st, DELIVERED)
        self.assertEqual(audit.of(DELIVERED), [detail])

    def test_attempt_once_unproven_on_wrong_hash(self):
        from core.audit import MemoryAuditSink
        from core.delivery import OneShotDelivery
        from core.gate import ManualGate
        ack = StdoutHashAck([PY, "-c", PRINT_WRONG])
        audit = MemoryAuditSink()
        delivery = OneShotDelivery(gate=ManualGate(), audit=audit)
        st, reason = attempt_once(delivery, "hello", ack, ack.prove)
        self.assertEqual(st, DROPPED)
        self.assertIn("unproven", reason)


if __name__ == "__main__":
    unittest.main()
