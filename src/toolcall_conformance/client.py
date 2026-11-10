"""Raw HTTP client built on the standard library.

It keeps the *original* response text and SSE lines so a failing check can
be reproduced from the JSONL record.
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

MOCK_HEADER = "X-Toolcall-Conformance-Mock"


class ConnectError(Exception):
    """The server could not be reached at all (refused, DNS failure...)."""


@dataclass
class Exchange:
    """One request and the raw answer to it."""

    scenario: str
    request: dict[str, Any]
    status: int = 0
    headers: dict[str, str] = field(default_factory=dict)
    text: str = ""  # body for non-stream requests, joined SSE lines otherwise
    sse_lines: list[str] = field(default_factory=list)
    error: str = ""  # timeout or transport problem after connecting

    @property
    def is_mock(self) -> bool:
        return any(k.lower() == MOCK_HEADER.lower() for k in self.headers)

    def json(self) -> dict[str, Any] | None:
        try:
            value = json.loads(self.text)
        except (json.JSONDecodeError, ValueError):
            return None
        return value if isinstance(value, dict) else None


def chat_url(base_url: str) -> str:
    return base_url.rstrip("/") + "/chat/completions"


def build_headers(api_key: str | None, extra: dict[str, str] | None) -> dict[str, str]:
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    headers.update(extra or {})
    return headers


def post_chat(
    base_url: str,
    body: dict[str, Any],
    scenario: str,
    *,
    api_key: str | None = None,
    extra_headers: dict[str, str] | None = None,
    timeout: float = 180.0,
) -> Exchange:
    """POST ``body`` to ``<base_url>/chat/completions`` and collect the raw answer.

    Raises ``ConnectError`` when the server cannot be reached. Timeouts and
    HTTP error statuses are returned inside the ``Exchange`` instead.
    """
    url = chat_url(base_url)
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=build_headers(api_key, extra_headers), method="POST")
    ex = Exchange(scenario=scenario, request=body)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (http(s) validated by CLI)
            ex.status = resp.status
            ex.headers = dict(resp.headers.items())
            _read_body(resp, ex, bool(body.get("stream")))
    except urllib.error.HTTPError as err:
        ex.status = err.code
        ex.headers = dict(err.headers.items()) if err.headers else {}
        ex.text = err.read().decode("utf-8", "replace")
    except urllib.error.URLError as err:
        if isinstance(err.reason, (socket.timeout, TimeoutError)):
            ex.error = f"timed out after {timeout:g}s"
        else:
            raise ConnectError(f"cannot connect to {url}: {err.reason}") from err
    except (socket.timeout, TimeoutError):
        ex.error = f"timed out after {timeout:g}s"
    except OSError as err:
        ex.error = f"transport error: {err}"
    return ex


def _read_body(resp: Any, ex: Exchange, stream: bool) -> None:
    """Read the body; keep what arrived even if the connection breaks midway."""
    try:
        if stream and "text/event-stream" in resp.headers.get("Content-Type", ""):
            for raw in resp:
                ex.sse_lines.append(raw.decode("utf-8", "replace").rstrip("\r\n"))
            ex.text = "\n".join(ex.sse_lines)
        else:
            ex.text = resp.read().decode("utf-8", "replace")
            if stream:
                ex.sse_lines = ex.text.splitlines()
    except (socket.timeout, TimeoutError):
        ex.error = "timed out while reading the response"
    except OSError as err:
        ex.error = f"connection broke while reading: {err}"
