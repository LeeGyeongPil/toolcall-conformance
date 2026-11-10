"""Core wire-format checks: non-stream shape, content leak, arguments, SSE assembly, round trip."""

from __future__ import annotations

import re

from ..assemble import assemble
from ..scenarios import TOOL_SCHEMAS
from ..sse import parse_sse
from . import FAIL, PASS, SKIP, CheckResult, register
from .common import http_problem, message_of, validate_args

LEAK_PATTERNS = [
    ("<tool_call>", re.compile(r"<tool_call>")),
    ("[TOOL_CALLS]", re.compile(r"\[TOOL_CALLS\]")),
    ("<|python_tag|>", re.compile(r"<\|python_tag\|>")),
    ("JSON with a tool name", re.compile(r"\"name\"\s*:\s*\"(?:%s)\"" % "|".join(TOOL_SCHEMAS))),
    ("function-call text", re.compile(r"\b(?:%s)\s*\(" % "|".join(TOOL_SCHEMAS))),
]


@register("nonstream_basic", "basic", "Non-stream message.tool_calls (id, type, name, arguments string) and finish_reason")
def nonstream_basic(ctx) -> CheckResult:
    ex = ctx.get("basic")
    res = CheckResult("nonstream_basic", FAIL, scenarios=["basic"])
    if problem := http_problem(ex):
        res.reason = problem
        return res
    got = message_of(ex)
    if got is None:
        res.reason = "response has no choices[0].message"
        return res
    msg, finish = got
    calls = msg.get("tool_calls") or []
    if not calls:
        if not (msg.get("content") or "").strip() and finish == "stop":
            res.reason = "empty content with stop: no tool call and no text"
        else:
            res.reason = f"no tool_calls in message (finish_reason={finish!r}, content={str(msg.get('content'))[:60]!r})"
        return res
    for i, call in enumerate(calls):
        fn = call.get("function") or {}
        if not call.get("id"):
            res.reason = f"tool_calls[{i}] has no id"
        elif call.get("type") != "function":
            res.reason = f"tool_calls[{i}].type is {call.get('type')!r}, expected 'function'"
        elif fn.get("name") not in TOOL_SCHEMAS:
            res.reason = f"tool_calls[{i}] names unknown tool {fn.get('name')!r}"
        elif not isinstance(fn.get("arguments"), str):
            res.reason = f"tool_calls[{i}].function.arguments must be a JSON string"
        if res.reason:
            return res
    if finish != "tool_calls":
        res.reason = f"finish_reason is {finish!r}, expected 'tool_calls'"
        return res
    res.grade = PASS
    res.info = {"tool_calls": len(calls), "extra_call_fields": sorted(set().union(*[set(c) for c in calls]) - {"id", "type", "function"})}
    return res


@register("content_leak", "leak", "Tool call text leaking into content (thinking-token fields are ignored)")
def content_leak(ctx) -> CheckResult:
    res = CheckResult("content_leak", PASS, scenarios=["basic", "stream"])
    found: list[str] = []
    texts: dict[str, str] = {}
    basic = ctx.get("basic")
    if not http_problem(basic) and (got := message_of(basic)):
        texts["non-stream"] = str(got[0].get("content") or "")
    stream = ctx.get("stream")
    if not http_problem(stream):
        texts["stream"] = assemble(parse_sse(stream.sse_lines).chunks).content
    if not texts:
        return CheckResult("content_leak", SKIP, "no usable response to inspect", scenarios=res.scenarios)
    for where, text in texts.items():
        for label, pattern in LEAK_PATTERNS:
            if pattern.search(text):
                found.append(f"{label} ({where})")
    if found:
        res.grade, res.reason = FAIL, "tool call text found in content: " + ", ".join(found)
        res.info = {"patterns": found}
    return res


@register("args_schema", "args", "arguments parse as JSON and satisfy the tool schema (required, basic types)")
def args_schema(ctx) -> CheckResult:
    res = CheckResult("args_schema", PASS, scenarios=["basic", "stream"])
    checked = 0
    basic = ctx.get("basic")
    if not http_problem(basic) and (got := message_of(basic)):
        for call in got[0].get("tool_calls") or []:
            fn = call.get("function") or {}
            checked += 1
            if problem := validate_args(fn.get("name", ""), fn.get("arguments")):
                return CheckResult("args_schema", FAIL, f"non-stream: {problem}", scenarios=res.scenarios)
    stream = ctx.get("stream")
    if not http_problem(stream):
        for call in assemble(parse_sse(stream.sse_lines).chunks).calls:
            checked += 1
            if problem := validate_args(call.name, call.arguments):
                return CheckResult("args_schema", FAIL, f"stream: {problem}", scenarios=res.scenarios)
    if not checked:
        return CheckResult("args_schema", SKIP, "no tool calls to validate", scenarios=res.scenarios)
    res.info = {"validated_calls": checked}
    return res


@register("stream_assembly", "stream", "Streamed delta.tool_calls assemble by index; id/name present; finish_reason")
def stream_assembly(ctx) -> CheckResult:
    ex = ctx.get("stream")
    res = CheckResult("stream_assembly", FAIL, scenarios=["stream"])
    if problem := http_problem(ex):
        res.reason = problem
        return res
    parsed = parse_sse(ex.sse_lines)
    if not parsed.chunks:
        res.reason = "no parsable SSE data chunks"
        return res
    asm = assemble(parsed.chunks)
    res.info = {
        "arg_fragments": asm.arg_fragments,
        "thinking_fields": asm.thinking_fields,
        "extra_delta_fields": asm.extra_fields,
        "finish_reason": asm.finish_reason,
    }
    if asm.missing_index:
        res.info["repairable"] = asm.repairable
        res.reason = f"missing index in delta.tool_calls (chunks {asm.missing_index[:5]})"
        return res
    if not asm.calls:
        res.reason = f"no tool calls in the stream (finish_reason={asm.finish_reason!r})"
        return res
    for call in asm.calls:
        if not call.id or not call.name:
            res.reason = f"call {call.index} lacks {'id' if not call.id else 'name'}"
            return res
    if asm.finish_reason != "tool_calls":
        res.reason = f"final finish_reason is {asm.finish_reason!r}, expected 'tool_calls'"
        return res
    res.grade = PASS
    return res


@register("stream_terminator", "done", "Stream ends with `data: [DONE]`")
def stream_terminator(ctx) -> CheckResult:
    ex = ctx.get("stream")
    res = CheckResult("stream_terminator", FAIL, scenarios=["stream"])
    if problem := http_problem(ex):
        res.reason = problem
    elif not parse_sse(ex.sse_lines).done:
        res.reason = "stream ended without `data: [DONE]`"
    else:
        res.grade = PASS
    return res


@register("roundtrip", "trip", "assistant tool_calls + tool message (tool_call_id) accepted; final answer with stop")
def roundtrip(ctx) -> CheckResult:
    ex = ctx.get("roundtrip")
    res = CheckResult("roundtrip", FAIL, scenarios=["roundtrip"])
    if problem := http_problem(ex):
        res.reason = problem
        return res
    got = message_of(ex)
    if got is None:
        res.reason = "response has no choices[0].message"
        return res
    msg, finish = got
    if msg.get("tool_calls"):
        res.reason = "server called a tool again instead of answering with the tool result"
    elif not (msg.get("content") or "").strip():
        res.reason = "empty final answer after the tool result"
    elif finish != "stop":
        res.reason = f"final finish_reason is {finish!r}, expected 'stop'"
    else:
        res.grade = PASS
    return res
