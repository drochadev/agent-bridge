"""HTTP slot adapter: thin JSON skin over OneShotDelivery.

Endpoints (single global slot, v0.1):
  POST /slot/put      {"text": "..."} -> 201 {"id"} | 422 {"reason"}
  GET  /slot/take                       -> 200 {"item": {...} | null}
  POST /slot/confirm  {"id", "ok", "detail"?} -> 200 | 422

Mapping: ok=true -> settle(id, "delivered"); ok=false -> settle(id, "dropped",
detail). Rejected settles (wrong id, duplicate, unknown) -> 422. Nothing is
ever re-offered.

Deliberately NOT carried over from legacy servers: CORS headers, internal
exception exposure, per-poll logging, attempts counters, conversation tags,
or any chat/agent/window-system concepts.

SlotApp holds the routing logic with no sockets so tests never need a live
server. serve() binds localhost by default; JSON errors and unexpected
failures become 400/500 with generic messages (no internals leak).
"""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

from core.delivery import ACCEPTED, DELIVERED, DROPPED

MAX_BODY = 1_000_000


class SlotApp:
    """Pure routing over an injected OneShotDelivery. No sockets, no I/O."""

    def __init__(self, delivery):
        self._delivery = delivery

    def post_put(self, body):
        if not isinstance(body, dict) or not isinstance(body.get("text"), str):
            return 422, {"ok": False, "reason": "invalid-text"}
        status, detail = self._delivery.put(body["text"])
        if status == ACCEPTED:
            return 201, {"ok": True, "id": detail}
        return 422, {"ok": False, "reason": detail}

    def get_take(self):
        item = self._delivery.take()
        return 200, {"ok": True, "item": item}

    def post_confirm(self, body):
        if not isinstance(body, dict) or not isinstance(body.get("id"), str):
            return 422, {"ok": False, "reason": "invalid-id"}
        ok = body.get("ok")
        if ok is True:
            status, detail = self._delivery.settle(body["id"], DELIVERED)
        elif ok is False:
            status, detail = self._delivery.settle(
                body["id"], DROPPED, body.get("detail") or body["id"])
        else:
            return 422, {"ok": False, "reason": "invalid-ok"}
        if status in (DELIVERED, DROPPED):
            return 200, {"ok": True, "result": status, "detail": detail}
        return 422, {"ok": False, "reason": detail}


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
    app = None  # SlotApp, injected by serve()
    server_version = "SlotApp/0.1"

    def log_message(self, *args):
        pass  # no per-request logging (polls would own the disk)

    def _send(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _route(self, method):
        try:
            if method == "GET" and self.path == "/slot/take":
                return self.app.get_take()
            if method == "POST" and self.path == "/slot/put":
                body, err = _read_json(self)
                if err:
                    return 400, {"ok": False, "reason": err}
                return self.app.post_put(body)
            if method == "POST" and self.path == "/slot/confirm":
                body, err = _read_json(self)
                if err:
                    return 400, {"ok": False, "reason": err}
                return self.app.post_confirm(body)
            return 404, {"ok": False, "reason": "unknown-route"}
        except Exception:
            return 500, {"ok": False, "reason": "internal-error"}

    def do_GET(self):
        self._send(*self._route("GET"))

    def do_POST(self):
        self._send(*self._route("POST"))


def serve(delivery, host="127.0.0.1", port=18765):
    """Run the slot server. Localhost by default. Blocks (serve_forever)."""
    handler = type("BoundHandler", (_Handler,), {"app": SlotApp(delivery)})
    HTTPServer((host, port), handler).serve_forever()
