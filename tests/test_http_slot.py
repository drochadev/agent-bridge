"""Behavior tests for adapters.http_slot (SlotApp contract; no sockets)."""
import unittest

from adapters.http_slot import SlotApp, serve
from core.audit import MemoryAuditSink
from core.delivery import OneShotDelivery
from core.gate import ManualGate


def make(open_=True, **kwargs):
    audit = MemoryAuditSink()
    gate = ManualGate(open_)
    delivery = OneShotDelivery(gate=gate, audit=audit, **kwargs)
    return SlotApp(delivery), delivery, audit, gate


class HttpSlotTest(unittest.TestCase):
    def test_put_valid(self):
        app, _, _, _ = make()
        code, res = app.post_put({"text": "hello"})
        self.assertEqual(code, 201)
        self.assertTrue(res["ok"])
        self.assertRegex(res["id"], r"^msg_[0-9a-f]{12}$")

    def test_put_invalid(self):
        app, _, _, _ = make()
        for bad in ({"text": ""}, {"text": "   "}, {"text": 123},
                    {"nope": 1}, "string", [1], None):
            code, res = app.post_put(bad)
            self.assertEqual(code, 422)
            self.assertFalse(res["ok"])

    def test_take_with_item(self):
        app, _, _, _ = make()
        _, put_res = app.post_put({"text": "hello"})
        code, res = app.get_take()
        self.assertEqual(code, 200)
        self.assertEqual(res["item"],
                         {"id": put_res["id"], "body": "hello"})

    def test_take_empty(self):
        app, _, _, _ = make()
        code, res = app.get_take()
        self.assertEqual((code, res), (200, {"ok": True, "item": None}))

    def test_take_once(self):
        app, _, _, _ = make()
        app.post_put({"text": "hello"})
        self.assertIsNotNone(app.get_take()[1]["item"])
        self.assertIsNone(app.get_take()[1]["item"])

    def test_confirm_delivered(self):
        app, _, audit, _ = make()
        _, put_res = app.post_put({"text": "hello"})
        item = app.get_take()[1]["item"]
        code, res = app.post_confirm({"id": item["id"], "ok": True})
        self.assertEqual(code, 200)
        self.assertEqual(res["result"], "delivered")
        self.assertEqual(audit.of("delivered"), [put_res["id"]])

    def test_confirm_dropped(self):
        app, _, audit, _ = make()
        app.post_put({"text": "hello"})
        item = app.get_take()[1]["item"]
        code, res = app.post_confirm({"id": item["id"], "ok": False,
                                      "detail": "no-proof"})
        self.assertEqual(code, 200)
        self.assertEqual(res["result"], "dropped")
        self.assertIn("no-proof", audit.of("dropped")[0])

    def test_confirm_wrong_id(self):
        app, _, audit, _ = make()
        app.post_put({"text": "hello"})
        app.get_take()
        code, res = app.post_confirm({"id": "msg_missing", "ok": True})
        self.assertEqual(code, 422)
        self.assertFalse(res["ok"])
        self.assertEqual(audit.of("delivered"), [])

    def test_confirm_duplicate(self):
        app, _, audit, _ = make()
        app.post_put({"text": "hello"})
        item = app.get_take()[1]["item"]
        self.assertEqual(app.post_confirm({"id": item["id"], "ok": True})[0],
                         200)
        code, _ = app.post_confirm({"id": item["id"], "ok": True})
        self.assertEqual(code, 422)
        self.assertEqual(len(audit.of("delivered")), 1)

    def test_confirm_invalid_shapes(self):
        app, _, _, _ = make()
        for bad in ({"ok": True}, {"id": 1, "ok": True},
                    {"id": "x", "ok": "yes"}, {"id": "x"}, None, [1]):
            code, res = app.post_confirm(bad)
            self.assertEqual(code, 422)

    def test_gate_closed(self):
        app, _, _, gate = make(open_=False)
        gate.set(False, "paused")
        code, res = app.post_put({"text": "hello"})
        self.assertEqual(code, 422)
        self.assertIn("gate-closed", res["reason"])

    def test_dedupe(self):
        app, _, _, _ = make()
        self.assertEqual(app.post_put({"text": "same"})[0], 201)
        app.get_take()
        code, res = app.post_put({"text": "same"})
        self.assertEqual(code, 422)
        self.assertIn("duplicate", res["reason"])

    def test_overwrite_audited_as_superseded(self):
        app, _, audit, _ = make()
        _, first = app.post_put({"text": "first"})
        app.post_put({"text": "second"})
        self.assertEqual(audit.of("superseded"), [first["id"]])
        self.assertEqual(app.get_take()[1]["item"]["body"], "second")

    def test_delegates_to_delivery(self):
        calls = []

        class SpyDelivery:
            def put(self, text):
                calls.append(("put", text))
                return "accepted", "msg_spy"

            def take(self):
                calls.append(("take",))
                return {"id": "msg_spy", "body": "x"}

            def settle(self, item_id, outcome, reason=None):
                calls.append(("settle", item_id, outcome, reason))
                return outcome, item_id

        app = SlotApp(SpyDelivery())
        app.post_put({"text": "hi"})
        app.get_take()
        app.post_confirm({"id": "msg_spy", "ok": False, "detail": "d"})
        self.assertEqual(calls, [("put", "hi"), ("take",),
                                 ("settle", "msg_spy", "dropped", "d")])

    def test_serve_defaults_to_localhost(self):
        import inspect
        sig = inspect.signature(serve)
        self.assertEqual(sig.parameters["host"].default, "127.0.0.1")

    def test_default_port_is_fixed_and_unprivileged(self):
        # Signature-level only: never binds a real port, so the test cannot
        # depend on what the system currently occupies.
        import inspect
        port = inspect.signature(serve).parameters["port"].default
        self.assertEqual(port, 18765)
        self.assertGreater(port, 1024)


class LiveServerTest(unittest.TestCase):
    """Real HTTPServer on an ephemeral localhost port (never the default).

    Exercises request → HTTPServer → handler → SlotApp → Delivery. Each
    test shuts the server down and joins its thread; a failing teardown
    fails loudly instead of leaking sockets.
    """

    def setUp(self):
        import threading
        from http.server import HTTPServer

        import adapters.http_slot as slot_mod

        audit = MemoryAuditSink()
        delivery = OneShotDelivery(gate=ManualGate(), audit=audit)
        handler = type("TestHandler", (slot_mod._Handler,),
                       {"app": SlotApp(delivery)})
        self.server = HTTPServer(("127.0.0.1", 0), handler)
        self.port = self.server.server_address[1]
        self.assertNotEqual(self.port, 18765)
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={"poll_interval": 0.01},
                                       daemon=True)
        self.thread.start()
        self.addCleanup(self._teardown)
        self.base = f"http://127.0.0.1:{self.port}"
        self.audit = audit

    def _teardown(self):
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()
        self.assertFalse(self.thread.is_alive())

    def _request(self, method, path, body=None, raw=None):
        import json
        import urllib.request
        data = raw if raw is not None else (
            json.dumps(body).encode() if body is not None else None)
        req = urllib.request.Request(self.base + path, data=data,
                                     method=method)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode())

    def test_put_take_confirm_flow(self):
        code, res = self._request("POST", "/slot/put", {"text": "hello"})
        self.assertEqual(code, 201)
        code, res = self._request("GET", "/slot/take")
        self.assertEqual((code, res["item"]["body"]), (200, "hello"))
        code, res = self._request("POST", "/slot/confirm",
                                  {"id": res["item"]["id"], "ok": True})
        self.assertEqual(code, 200)
        self.assertEqual(res["result"], "delivered")

    def test_unknown_route_is_404(self):
        code, res = self._request("GET", "/nope")
        self.assertEqual(code, 404)
        self.assertFalse(res["ok"])

    def test_invalid_json_is_400(self):
        code, res = self._request("POST", "/slot/put",
                                  raw=b"{not json")
        self.assertEqual(code, 400)
        self.assertFalse(res["ok"])

    def test_oversized_payload_rejected(self):
        # The server rejects without consuming the body, so a large upload
        # may surface here either as 400 or as a broken pipe when the server
        # closes early. Both prove rejection; afterwards the server must
        # still be healthy (no wedging, no state corruption).
        import urllib.error
        big = "x" * (1_000_001 + 100)
        try:
            code, res = self._request("POST", "/slot/put", {"text": big})
        except urllib.error.URLError:
            code, res = None, {"ok": False}
        self.assertIn(code, (400, None))
        self.assertFalse(res["ok"])
        code2, res2 = self._request("POST", "/slot/put", {"text": "alive"})
        self.assertEqual(code2, 201)
        self.assertTrue(res2["ok"])


if __name__ == "__main__":
    unittest.main()
