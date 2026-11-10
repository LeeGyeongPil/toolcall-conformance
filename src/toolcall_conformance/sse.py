"""Minimal Server-Sent Events parser for ``chat.completion.chunk`` streams."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SseParse:
    """Result of parsing raw SSE lines."""

    chunks: list[dict[str, Any]] = field(default_factory=list)  # JSON payloads in order
    done: bool = False  # saw ``data: [DONE]``
    errors: list[str] = field(default_factory=list)  # lines that were not valid JSON


def parse_sse(lines: list[str]) -> SseParse:
    """Parse raw SSE lines (``data: ...``). Comments (``:``) and blank lines are skipped."""
    out = SseParse()
    for raw in lines:
        line = raw.rstrip("\r\n")
        if not line or line.startswith(":"):
            continue
        if not line.startswith("data:"):
            continue  # event:/id:/retry: fields are not used by tool-call streams
        payload = line[len("data:"):].strip()
        if payload == "[DONE]":
            out.done = True
            continue
        try:
            value = json.loads(payload)
        except json.JSONDecodeError:
            out.errors.append(payload[:200])
            continue
        if isinstance(value, dict):
            out.chunks.append(value)
        else:
            out.errors.append(payload[:200])
    return out
