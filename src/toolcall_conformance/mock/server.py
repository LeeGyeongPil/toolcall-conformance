"""``/mode/<mode>/v1`` mock server (127.0.0.1) serving every deviation mode at once."""

from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from ..client import MOCK_HEADER
from .faults import MODES, Fault
from .model import BadRequest, Reply, arguments_json, call_id, respond

_PATH = re.compile(r"^(?:/mode/(?P<mode>[a-z_]+))?/v1/(?P<route>chat/completions|models)/?$")


def _chunk(model: str, delta: dict[str, Any], finish: str | None = None) -> dict[str, Any]:
    return {"id": "chatcmpl-mock", "object": "chat.completion.chunk", "created": 0, "model": model,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}


def _split(text: str, parts: int) -> list[str]:
    """Cut ``text`` into up to ``parts`` non-empty fragments."""
    size = max(1, -(-len(text) // parts))
    return [text[i:i + size] for i in range(0, len(text), size)]


def build_message(reply: Reply, fault: Fault) -> tuple[dict[str, Any], str]:
    """Non-stream ``message`` and ``finish_reason``."""
    msg: dict[str, Any] = {"role": "assistant", "content": reply.text or None}
    if fault.reasoning:
        msg["reasoning"] = "The user wants a tool call."
    if not reply.calls:
        return msg, "stop"
    if fault.leak_content:
        msg["content"] = "\n".join(
            "<tool_call>\n" + json.dumps({"name": c["name"], "arguments": c["arguments"]}) + "\n</tool_call>"
            for c in reply.calls)
        return msg, "stop"
    if fault.empty_stop:
        msg["content"] = ""
        return msg, "stop"
    msg["tool_calls"] = [
        {"id": call_id(i), "type": "function",
         "function": {"name": c["name"], "arguments": arguments_json(c, bad=fault.bad_json)},
         **({"index": i} if fault.extra_index else {})}
        for i, c in enumerate(reply.calls)]
    return msg, "tool_calls"


def build_stream(reply: Reply, fault: Fault, model: str) -> list[str]:
    """SSE lines (``data: ...``) for a streamed answer."""
    chunks = [_chunk(model, {"role": "assistant", "content": ""})]  # like OpenAI: role-only first chunk
    if fault.reasoning:
        chunks += [_chunk(model, {"reasoning": "The user "}), _chunk(model, {"reasoning": "wants a tool."})]
    finish = "stop"
    if reply.calls and fault.leak_content:
        msg, finish = build_message(reply, fault)
        chunks += [_chunk(model, {"content": part}) for part in _split(msg["content"], 3)]
    elif reply.calls and fault.empty_stop:
        pass
    elif reply.calls:
        finish = "tool_calls"
        for i, c in enumerate(reply.calls):
            args = arguments_json(c, bad=fault.bad_json)
            head = {"index": i, "id": call_id(i), "type": "function", "function": {"name": c["name"]}}
            if fault.whole_args:
                head["function"]["arguments"] = args
                entries = [head]
            else:
                head["function"]["arguments"] = ""
                entries = [head] + [{"index": i, "function": {"arguments": frag}} for frag in _split(args, 3)]
            for entry in entries:
                if fault.drop_index:
                    entry.pop("index")
                chunks.append(_chunk(model, {"tool_calls": [entry]}))
    else:
        chunks += [_chunk(model, {"content": w + " "}) for w in reply.text.split()]
    chunks.append(_chunk(model, {}, finish))
    lines = [f"data: {json.dumps(c)}\n" for c in chunks]
    if not fault.no_done:
        lines.append("data: [DONE]\n")
    return lines


class _Handler(BaseHTTPRequestHandler):
    server: "_Server"

    def log_message(self, *_args: Any) -> None:  # keep test and demo output clean
        pass

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header(MOCK_HEADER, "1")
        self.end_headers()
        self.wfile.write(data)

    def _route(self) -> tuple[Fault, str] | None:
        m = _PATH.match(self.path.split("?")[0])
        if not m:
            self._send_json(404, {"error": {"message": f"no such route: {self.path}"}})
            return None
        mode = m.group("mode") or "good"
        if mode not in MODES:
            self._send_json(404, {"error": {"message": f"unknown mock mode {mode!r}; known: {', '.join(MODES)}"}})
            return None
        return MODES[mode], m.group("route")

    def do_GET(self) -> None:  # noqa: N802
        routed = self._route()
        if routed and routed[1] == "models":
            self._send_json(200, {"object": "list", "data": [{"id": "mock", "object": "model"}]})
        elif routed:
            self._send_json(405, {"error": {"message": "use POST"}})

    def do_POST(self) -> None:  # noqa: N802
        routed = self._route()
        if not routed:
            return
        fault, route = routed
        if route != "chat/completions":
            self._send_json(405, {"error": {"message": "use GET"}})
            return
        self.server.count()
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(body, dict):
                raise BadRequest("request body must be a JSON object")
            reply = respond(body, ignore_tool_choice=fault.ignore_tool_choice)
        except (BadRequest, json.JSONDecodeError) as err:
            self._send_json(400, {"error": {"message": str(err), "type": "invalid_request_error"}})
            return
        model = str(body.get("model", "mock"))
        if body.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header(MOCK_HEADER, "1")
            self.end_headers()  # no Content-Length: the body ends when the connection closes
            for line in build_stream(reply, fault, model):
                self.wfile.write((line + "\n").encode())
                self.wfile.flush()
            self.close_connection = True
            return
        msg, finish = build_message(reply, fault)
        self._send_json(200, {"id": "chatcmpl-mock", "object": "chat.completion", "created": 0, "model": model,
                              "choices": [{"index": 0, "message": msg, "finish_reason": finish}]})


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, addr: tuple[str, int]) -> None:
        super().__init__(addr, _Handler)
        self._lock = threading.Lock()
        self.requests = 0

    def count(self) -> None:
        with self._lock:
            self.requests += 1


class MockServer:
    """Start with ``with MockServer() as srv:``; ``srv.url('no_index')`` is a base URL."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self._httpd = _Server((host, port))
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return self._httpd.server_address[1]

    @property
    def request_count(self) -> int:
        """Number of chat-completion requests served so far."""
        return self._httpd.requests

    def url(self, mode: str = "good") -> str:
        if mode not in MODES:
            raise ValueError(f"unknown mock mode {mode!r}; choose from: {', '.join(MODES)}")
        return f"http://{self._httpd.server_address[0]}:{self.port}/mode/{mode}/v1"

    def start(self) -> "MockServer":
        self._thread = threading.Thread(target=self._httpd.serve_forever, name="mock-server", daemon=True)
        self._thread.start()
        return self

    def close(self) -> None:
        if self._thread is not None:
            self._httpd.shutdown()
            self._thread.join(timeout=5)
            self._thread = None
        self._httpd.server_close()

    def __enter__(self) -> "MockServer":
        return self.start()

    def __exit__(self, *_exc: object) -> None:
        self.close()
