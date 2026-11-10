"""Fixed tools, prompts and request bodies (temperature 0) shared by the checks."""

from __future__ import annotations

from typing import Any

TOOLS: list[dict[str, Any]] = [
    {"type": "function", "function": {
        "name": "get_weather",
        "description": "Get the current weather for a city.",
        "parameters": {"type": "object",
                       "properties": {"city": {"type": "string", "description": "City name, e.g. Seoul"}},
                       "required": ["city"]}}},
    {"type": "function", "function": {
        "name": "get_time",
        "description": "Get the current time in an IANA time zone.",
        "parameters": {"type": "object",
                       "properties": {"timezone": {"type": "string", "description": "e.g. Asia/Seoul"}},
                       "required": ["timezone"]}}},
]
TOOL_SCHEMAS = {t["function"]["name"]: t["function"]["parameters"] for t in TOOLS}

WEATHER_PROMPT = "What is the weather in Seoul right now? Use the available tools."
PARALLEL_PROMPT = "What is the weather in Seoul and in Busan right now? Use the available tools."
NO_TOOL_PROMPT = "Say hello in one short sentence."
ROUNDTRIP_CALL_ID = "call_conformance_1"


def _base(model: str, messages: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    return {"model": model, "messages": messages, "tools": TOOLS, "temperature": 0, **extra}


def _user(text: str) -> list[dict[str, Any]]:
    return [{"role": "user", "content": text}]


def build_request(name: str, model: str) -> dict[str, Any]:
    """Request body for scenario ``name`` (see ``SCENARIOS``)."""
    if name == "basic":
        return _base(model, _user(WEATHER_PROMPT))
    if name == "stream":
        return _base(model, _user(WEATHER_PROMPT), stream=True)
    if name == "choice_none":  # a prompt that *invites* a call, so ignoring `none` shows up
        return _base(model, _user(WEATHER_PROMPT), tool_choice="none")
    if name == "choice_required":  # a prompt that does *not* need a tool
        return _base(model, _user(NO_TOOL_PROMPT), tool_choice="required")
    if name == "choice_named":  # the prompt hints at get_weather, the request forces get_time
        return _base(model, _user(WEATHER_PROMPT),
                     tool_choice={"type": "function", "function": {"name": "get_time"}})
    if name == "parallel":
        return _base(model, _user(PARALLEL_PROMPT), parallel_tool_calls=True)
    if name == "roundtrip":
        messages = _user(WEATHER_PROMPT) + [
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": ROUNDTRIP_CALL_ID, "type": "function",
                 "function": {"name": "get_weather", "arguments": "{\"city\":\"Seoul\"}"}}]},
            {"role": "tool", "tool_call_id": ROUNDTRIP_CALL_ID,
             "content": "{\"temp_c\": 12, \"sky\": \"clear\"}"},
        ]
        return _base(model, messages)
    raise KeyError(name)


SCENARIOS = ("basic", "stream", "choice_none", "choice_required", "choice_named", "parallel", "roundtrip")
