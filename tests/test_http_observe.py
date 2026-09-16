"""Behavior tests for adapters.http_observe (pure app, no sockets)."""
import unittest

from adapters.http_observe import ObservationApp, serve
from adapters.observe import ObservationFeed


class HttpObserveTest(unittest.TestCase):
    def test_generating_is_idle(self):
        app = ObservationApp(ObservationFeed())
        code, res = app.post_observe({"generating": True, "finished": False,
                                      "texts": ["part"]})
        self.assertEqual(code, 200)
        self.assertEqual(res, {"ok": True, "status": "idle"})

    def test_finished_is_ready_with_text_only(self):
        app = ObservationFeed()
        app.observe({"generating": True, "finished": False, "texts": ["a"]})
        server = ObservationApp(app)
        code, res = server.post_observe({"generating": False, "finished": True,
                                         "texts": ["done"], "composer": {},
                                         "url": "https://x"})
        self.assertEqual(code, 200)
        self.assertEqual(res, {"ok": True, "status": "ready", "text": "done"})

    def test_invalid_envelope_rejected(self):
        app = ObservationApp(ObservationFeed())
        for bad in ({"texts": "nope"}, {"texts": [7]}, {},
                    {"generating": "yes", "texts": []}, "str", [1], None):
            code, res = app.post_observe(bad)
            self.assertEqual(code, 422)
            self.assertFalse(res["ok"])

    def test_error_reason_is_generic(self):
        app = ObservationApp(ObservationFeed())
        code, res = app.post_observe({"texts": [object()]})
        # object() is not JSON-serializable downstream, but here it fails
        # validation first with a short generic reason
        self.assertEqual(code, 422)
        self.assertLess(len(res["reason"]), 80)

    def test_serve_defaults(self):
        import inspect
        sig = inspect.signature(serve)
        self.assertEqual(sig.parameters["host"].default, "127.0.0.1")
        self.assertEqual(sig.parameters["port"].default, 18766)


if __name__ == "__main__":
    unittest.main()
