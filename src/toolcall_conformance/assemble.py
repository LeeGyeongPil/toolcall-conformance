"""Assemble streamed ``delta.tool_calls`` fragments and record deviations."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

THINKING_FIELDS = ("reasoning", "reasoning_content")
STANDARD_DELTA_FIELDS = {"role", "content", "tool_calls", "refusal", "function_call", *THINKING_FIELDS}


@dataclass
class Call:
    index: int
    id: str = ""
    name: str = ""
    arguments: str = ""


@dataclass
class Assembly:
    calls: list[Call] = field(default_factory=list)
    content: str = ""
    finish_reason: str | None = None
    missing_index: list[int] = field(default_factory=list)  # chunk numbers lacking ``index``
    arg_fragments: int = 0  # how many chunks carried ``arguments`` text
    thinking_fields: list[str] = field(default_factory=list)
    extra_fields: list[str] = field(default_factory=list)  # non-standard delta keys
    repairable: bool = False  # assembling is possible if missing index is repaired


def _assemble(chunks: list[dict[str, Any]], repair: bool) -> Assembly:
    asm = Assembly()
    by_index: dict[int, Call] = {}
    last: Call | None = None
    for n, chunk in enumerate(chunks):
        for choice in chunk.get("choices") or []:
            if choice.get("finish_reason"):
                asm.finish_reason = choice["finish_reason"]
            delta = choice.get("delta") or {}
            for key in delta:
                if key in THINKING_FIELDS and key not in asm.thinking_fields:
                    asm.thinking_fields.append(key)
                elif key not in STANDARD_DELTA_FIELDS and key not in asm.extra_fields:
                    asm.extra_fields.append(key)
            if isinstance(delta.get("content"), str):
                asm.content += delta["content"]
            for tc in delta.get("tool_calls") or []:
                fn = tc.get("function") or {}
                idx = tc.get("index")
                if not isinstance(idx, int):
                    if not repair:
                        if n not in asm.missing_index:
                            asm.missing_index.append(n)
                        continue
                    # repair: an entry that carries an id or a name starts a new call
                    if tc.get("id") or fn.get("name") or last is None:
                        idx = len(by_index)
                    else:
                        idx = last.index
                call = by_index.setdefault(idx, Call(index=idx))
                last = call
                if tc.get("id"):
                    call.id = tc["id"]
                if fn.get("name"):
                    call.name += fn["name"]
                if isinstance(fn.get("arguments"), str) and fn["arguments"] != "":
                    call.arguments += fn["arguments"]
                    asm.arg_fragments += 1
    asm.calls = [by_index[i] for i in sorted(by_index)]
    return asm


def assemble(chunks: list[dict[str, Any]]) -> Assembly:
    """Assemble strictly (entries without ``index`` are dropped and recorded).

    When ``index`` is missing, a second repairing pass tells whether a lenient
    client could still make sense of the stream (``repairable``).
    """
    strict = _assemble(chunks, repair=False)
    if strict.missing_index:
        fixed = _assemble(chunks, repair=True)
        strict.repairable = bool(fixed.calls) and all(c.name and _is_json(c.arguments) for c in fixed.calls)
    return strict


def _is_json(text: str) -> bool:
    try:
        json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return False
    return True
