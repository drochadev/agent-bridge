"""HTTP observation adapter: envelopes in, finished text out. Never delivery.

POST /observe {"generating","finished","texts",...} -> validate -> feed ->
  200 {"ok": true, "status": "idle"}                        (nothing finished)
  200 {"ok": true, "status": "ready", "text": "..."}        (finished text)
  422 {"ok": false, "reason": ...}                          (invalid envelope)

Observation and delivery are different concepts on purpose: this endpoint
never touches a slot, a gate, or an audit sink. Unknown envelope fields are
ignored by validation and never leak into the result. Localhost by default;
no CORS; generic errors only.
"""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

from core.envelope import ValidationError, validate

MAX_BODY = 1_000_000


class ObservationApp:
    """Pure routing over an injected ObservationFeed. No sockets, no I/O."""

    def __init__(self, feed):
        self._feed = feed

    def post_observe(self, body):
        if not isinstance(body, dict):
            return 422, {"ok": False, "reason": "invalid-envelope"}
        try:
            observation = validate(body)
        except ValidationError as exc:
            return 422, {"ok": False, "reason": str(exc)}
        text = self._feed.observe(observation)
        if text is None:
            return 200, {"ok": True, "status": "idle"}
        return 200, {"ok": True, "status": "ready", "text": text}


def _read_json(handler):
    try:
        length = int(handler.headers.get("Content-Length", "0"))
    except ValueError:
        length = 0
    if length <= 0 or length > MAX_BODY:
        return None, "empty-or-too-large"
    try:
        raw = handler.rfile.read(length)
    except Exception:
        return None, "unreadable"
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except Exception:
        return None, "invalid-json"
    if not isinstance(parsed, dict):
        return None, "invalid-json"
    return parsed, ""


class _Handler(BaseHTTPRequestHandler):
    app = None  # ObservationApp, injected by serve()
    server_version = "ObserveApp/0.1"

    def log_message(self, *args):
        pass  # no per-request logging

    def _send(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _route(self, method):
        try:
            if method == "POST" and self.path == "/observe":
                body, err = _read_json(self)
                if err:
                    return 400, {"ok": False, "reason": err}
                return self.app.post_observe(body)
            return 404, {"ok": False, "reason": "unknown-route"}
        except Exception:
            return 500, {"ok": False, "reason": "internal-error"}

    def do_POST(self):
        self._send(*self._route("POST"))

    def do_GET(self):
        self._send(404, {"ok": False, "reason": "unknown-route"})


def serve(feed, host="127.0.0.1", port=18766):
    """Run the observation server. Localhost by default. Blocks."""
    handler = type("BoundHandler", (_Handler,), {"app": ObservationApp(feed)})
    HTTPServer((host, port), handler).serve_forever()
