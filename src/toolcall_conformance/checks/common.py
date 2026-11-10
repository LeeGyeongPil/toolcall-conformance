"""Helpers shared by the checks."""

from __future__ import annotations

import json
from typing import Any

from ..client import Exchange
from ..scenarios import TOOL_SCHEMAS

_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,), "number": (int, float), "integer": (int,), "boolean": (bool,),
    "object": (dict,), "array": (list,),
}


def http_problem(ex: Exchange) -> str:
    """Return a one-line reason when the exchange did not produce a usable 200, else ''."""
    if ex.error:
        return ex.error
    if ex.status != 200:
        return f"HTTP {ex.status}: {ex.text.strip()[:160]}"
    return ""


def message_of(ex: Exchange) -> tuple[dict[str, Any], str | None] | None:
    """(message, finish_reason) of a non-stream answer, or None if malformed."""
    data = ex.json()
    try:
        choice = data["choices"][0]  # type: ignore[index]
        return choice["message"], choice.get("finish_reason")
    except (TypeError, KeyError, IndexError):
        return None


def validate_args(name: str, raw: Any) -> str:
    """Check ``arguments`` against the fixed tool schema; return a problem or ''."""
    if not isinstance(raw, str):
        return f"arguments is {type(raw).__name__}, expected a JSON string"
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as err:
        return f"arguments is not valid JSON ({err.msg}): {raw[:80]!r}"
    schema = TOOL_SCHEMAS.get(name)
    if schema is None:
        return f"unknown tool name {name!r}"
    if not isinstance(value, dict):
        return "arguments JSON is not an object"
    for key in schema.get("required", []):
        if key not in value:
            return f"missing required argument {key!r}"
    for key, spec in schema.get("properties", {}).items():
        if key in value:
            allowed = _TYPES.get(spec.get("type", ""), ())
            if allowed and (not isinstance(value[key], allowed) or (spec["type"] != "boolean" and isinstance(value[key], bool))):
                return f"argument {key!r} should be {spec['type']}"
    return ""
