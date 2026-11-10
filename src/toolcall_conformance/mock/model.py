"""Deterministic rule-based "model": picks tools from keywords in the last user message."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

CITIES = ["Seoul", "Busan", "Tokyo", "Paris", "London"]


class BadRequest(Exception):
    """The request is invalid; the server answers HTTP 400 with this message."""


@dataclass
class Reply:
    text: str = ""
    calls: list[dict[str, Any]] = field(default_factory=list)  # {"name": str, "arguments": dict}


def _tool_names(body: dict[str, Any]) -> list[str]:
    names = []
    for tool in body.get("tools") or []:
        fn = (tool or {}).get("function") or {}
        if fn.get("name"):
            names.append(fn["name"])
    return names


def _default_args(name: str, text: str) -> dict[str, Any]:
    if name == "get_time":
        return {"timezone": "Asia/Seoul" if "seoul" in text else "UTC"}
    found = _cities(text)
    return {"city": found[0] if found else "Seoul"}


def _cities(text: str) -> list[str]:
    hits = [(text.find(c.lower()), c) for c in CITIES if c.lower() in text]
    return [c for _, c in sorted(hits)]


def _validate_tool_messages(messages: list[dict[str, Any]]) -> None:
    """A ``tool`` message must answer a tool call issued earlier by the assistant."""
    issued: set[str] = set()
    for msg in messages:
        if msg.get("role") == "assistant":
            for tc in msg.get("tool_calls") or []:
                if tc.get("id"):
                    issued.add(tc["id"])
        elif msg.get("role") == "tool":
            tid = msg.get("tool_call_id")
            if not tid or tid not in issued:
                raise BadRequest(f"tool message has tool_call_id {tid!r} that matches no assistant tool call")


def respond(body: dict[str, Any], *, ignore_tool_choice: bool = False) -> Reply:
    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        raise BadRequest("`messages` must be a non-empty list")
    _validate_tool_messages(messages)

    last = messages[-1]
    if last.get("role") == "tool":
        return Reply(text=f"The tool returned: {last.get('content')}. That answers your question.")

    user = next((m for m in reversed(messages) if m.get("role") == "user"), {})
    text = str(user.get("content") or "").lower()
    names = _tool_names(body)
    choice = body.get("tool_choice", "auto")
    if ignore_tool_choice:
        choice = "auto"
    if not names or choice == "none":
        return Reply(text="Here is a plain answer without calling a tool.")

    wanted: list[dict[str, Any]] = []
    if "weather" in text and "get_weather" in names:
        cities = _cities(text) or ["Seoul"]
        wanted += [{"name": "get_weather", "arguments": {"city": c}} for c in cities]
    if "time" in text and "get_time" in names:
        wanted.append({"name": "get_time", "arguments": _default_args("get_time", text)})

    if isinstance(choice, dict):  # forced function
        forced = (choice.get("function") or {}).get("name")
        if forced not in names:
            raise BadRequest(f"tool_choice names unknown function {forced!r}")
        wanted = [c for c in wanted if c["name"] == forced] or [
            {"name": forced, "arguments": _default_args(forced, text)}
        ]
        return Reply(calls=wanted[:1])
    if choice == "required" and not wanted:
        wanted = [{"name": names[0], "arguments": _default_args(names[0], text)}]
    if body.get("parallel_tool_calls") is False:
        wanted = wanted[:1]
    return Reply(calls=wanted) if wanted else Reply(text="I can answer that without a tool.")


def call_id(i: int) -> str:
    return f"call_mock_{i + 1}"


def arguments_json(call: dict[str, Any], *, bad: bool) -> str:
    """Compact JSON string; ``bad`` cuts it short so it no longer parses."""
    s = json.dumps(call["arguments"], separators=(",", ":"))
    return s[:-2] if bad else s


