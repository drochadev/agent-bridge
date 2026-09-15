"""Behavior tests for core.gate and core.audit contracts."""
import unittest

from core.audit import MemoryAuditSink, NullAuditSink
from core.gate import Gate, ManualGate


class GateTest(unittest.TestCase):
    def test_manual_gate_defaults_open(self):
        self.assertEqual(ManualGate().is_open(), (True, ""))

    def test_manual_gate_set_closed_with_reason(self):
        gate = ManualGate()
        gate.set(False, "paused")
        self.assertEqual(gate.is_open(), (False, "paused"))
        gate.set(True)
        self.assertEqual(gate.is_open(), (True, ""))

    def test_manual_gate_satisfies_protocol(self):
        self.assertIsInstance(ManualGate(), Gate)


class AuditSinkTest(unittest.TestCase):
    def test_memory_sink_records_and_filters(self):
        sink = MemoryAuditSink()
        sink.record("accepted", "m1")
        sink.record("dropped", "empty-text")
        self.assertEqual(sink.of("accepted"), ["m1"])
        self.assertEqual(sink.of("missing"), [])

    def test_null_sink_discards(self):
        sink = NullAuditSink()
        sink.record("accepted", "m1")  # must not raise, stores nothing
        self.assertFalse(hasattr(sink, "events"))


if __name__ == "__main__":
    unittest.main()
