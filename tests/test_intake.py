"""Behavior tests for core.intake (composition only, no I/O)."""
import unittest

from core.delivery import ACCEPTED, DROPPED, OneShotDelivery
from core.audit import MemoryAuditSink
from core.gate import ManualGate
from core.intake import Intake
from core.source import ManualSource

MSG = "[MSG]\nhello\n[/MSG]"


def process_all(source, deliver):
    intake = Intake(source, deliver)
    return intake, intake.process()


class IntakeTest(unittest.TestCase):
    def test_empty_source(self):
        intake, results = process_all(ManualSource(), lambda t: (ACCEPTED, "x"))
        self.assertEqual(results, [])
        self.assertIsNotNone(intake.token())

    def test_partial_item(self):
        src = ManualSource()
        src.upsert("m1", "half written")
        intake, results = process_all(src, lambda t: (ACCEPTED, "x"))
        self.assertEqual(results, [{"id": "m1", "version": 1,
                                    "disposition": "skipped"}])

    def test_partial_becomes_final(self):
        src = ManualSource()
        src.upsert("m1", "half written")
        intake = Intake(src, lambda t: (ACCEPTED, "x"))
        first = intake.process()
        self.assertEqual(first[0]["disposition"], "skipped")
        src.upsert("m1", MSG, final=True)
        second = intake.process()
        self.assertEqual(second, [{"id": "m1", "version": 2,
                                   "disposition": "accepted"}])

    def test_final_without_block(self):
        src = ManualSource()
        src.upsert("m1", "just a note", final=True)
        _, results = process_all(src, lambda t: (ACCEPTED, "x"))
        self.assertEqual(results, [{"id": "m1", "version": 1,
                                    "disposition": "no-message"}])

    def test_final_with_valid_block(self):
        seen = []
        src = ManualSource()
        src.upsert("m1", MSG, final=True)

        def deliver(text):
            seen.append(text)
            return ACCEPTED, "m9"

        _, results = process_all(src, deliver)
        self.assertEqual(seen, ["hello"])
        self.assertEqual(results, [{"id": "m1", "version": 1,
                                    "disposition": "accepted"}])

    def test_delivery_accepts(self):
        audit = MemoryAuditSink()
        delivery = OneShotDelivery(gate=ManualGate(), audit=audit)
        src = ManualSource()
        src.upsert("m1", MSG, final=True)
        _, results = process_all(src, delivery.put)
        self.assertEqual(results[0]["disposition"], "accepted")
        self.assertEqual(delivery.take()["body"], "hello")

    def test_delivery_rejects_on_gate(self):
        gate = ManualGate()
        gate.set(False, "paused")
        delivery = OneShotDelivery(gate=gate, audit=MemoryAuditSink())
        src = ManualSource()
        src.upsert("m1", MSG, final=True)
        _, results = process_all(src, delivery.put)
        self.assertEqual(results, [{"id": "m1", "version": 1,
                                    "disposition": "rejected"}])

    def test_delivery_rejects_duplicate(self):
        delivery = OneShotDelivery(gate=ManualGate(),
                                   audit=MemoryAuditSink())
        src = ManualSource()
        src.upsert("m1", MSG, final=True)
        intake = Intake(src, delivery.put)
        self.assertEqual(intake.process()[0]["disposition"], "accepted")
        src.upsert("m2", MSG, final=True)  # same content, new id
        second = intake.process()
        self.assertEqual(second, [{"id": "m2", "version": 1,
                                   "disposition": "rejected"}])

    def test_multiple_items_same_cycle(self):
        src = ManualSource()
        src.upsert("a", MSG, final=True)
        src.upsert("b", "partial")
        src.upsert("c", "note", final=True)
        _, results = process_all(src, lambda t: (ACCEPTED, "x"))
        self.assertEqual([(r["id"], r["disposition"]) for r in results],
                         [("a", "accepted"), ("b", "skipped"),
                          ("c", "no-message")])

    def test_exception_blocks_token_adoption(self):
        src = ManualSource()
        src.upsert("m1", MSG, final=True)

        def boom(text):
            raise RuntimeError("sink down")

        intake = Intake(src, boom)
        with self.assertRaises(RuntimeError):
            intake.process()
        self.assertIsNone(intake.token())  # not adopted
        # next pass retries the same version (nothing lost)
        intake2 = Intake(src, lambda t: (ACCEPTED, "x"))
        results = intake2.process()
        self.assertEqual(results[0]["disposition"], "accepted")

    def test_new_version_after_previous_token(self):
        src = ManualSource()
        src.upsert("m1", MSG, final=True)
        intake = Intake(src, lambda t: (ACCEPTED, "x"))
        intake.process()
        src.upsert("m1", MSG, final=True)  # same content, new version
        second = intake.process()
        self.assertEqual(second, [{"id": "m1", "version": 2,
                                   "disposition": "accepted"}])

    def test_two_independent_messages(self):
        src = ManualSource()
        src.upsert("a", "[MSG]\none\n[/MSG]", final=True)
        src.upsert("b", "[MSG]\ntwo\n[/MSG]", final=True)
        seen = []
        _, results = process_all(src, lambda t: seen.append(t) or (ACCEPTED, t))
        self.assertEqual(seen, ["one", "two"])
        self.assertEqual([r["disposition"] for r in results],
                         ["accepted", "accepted"])

    def test_token_internal_and_opaque(self):
        src = ManualSource()
        intake = Intake(src, lambda t: (ACCEPTED, "x"))
        self.assertIsNone(intake.token())
        src.upsert("m1", "partial")
        intake.process()
        token = intake.token()
        self.assertIsNotNone(token)
        # consumer never crafts tokens: only passes back; invalid rejected
        with self.assertRaises(ValueError):
            src.changes("forged")

    def test_extract_only_called_for_final(self):
        import core.intake as intake_mod
        calls = []
        real_extract = intake_mod.extract_block

        def spy(text):
            calls.append(text)
            return real_extract(text)

        intake_mod.extract_block = spy
        try:
            src = ManualSource()
            src.upsert("p", "partial text")
            src.upsert("f", MSG, final=True)
            Intake(src, lambda t: (ACCEPTED, "x")).process()
        finally:
            intake_mod.extract_block = real_extract
        self.assertEqual(calls, [MSG])

    def test_final_malformed_block(self):
        src = ManualSource()
        src.upsert("m1", "[MSG]\n   \n[/MSG]", final=True)
        _, results = process_all(src, lambda t: (ACCEPTED, "x"))
        self.assertEqual(results, [{"id": "m1", "version": 1,
                                    "disposition": "invalid-message"}])

    def test_deliver_only_called_with_valid_block(self):
        calls = []
        src = ManualSource()
        src.upsert("a", "no block here", final=True)
        src.upsert("b", "[MSG]\n \n[/MSG]", final=True)  # empty block
        src.upsert("c", MSG, final=True)
        Intake(src, lambda t: calls.append(t) or (ACCEPTED, "x")).process()
        self.assertEqual(calls, ["hello"])


if __name__ == "__main__":
    unittest.main()
