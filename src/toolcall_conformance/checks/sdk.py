"""Client-side view: let the official ``openai`` SDK assemble the same stream."""

from __future__ import annotations

from importlib.metadata import version

from ..assemble import assemble
from ..sse import parse_sse
from . import ERROR, FAIL, PASS, CheckResult, register


@register("sdk_stream_compat", "sdk", "The official openai SDK stream helper assembles the same request without error")
def sdk_stream_compat(ctx) -> CheckResult:
    from openai import APIConnectionError, OpenAI

    sdk_version = version("openai")
    res = CheckResult("sdk_stream_compat", FAIL, sdk_version=sdk_version, scenarios=[])
    body = ctx.request("stream")
    client = OpenAI(base_url=ctx.target.base_url, api_key=ctx.target.api_key or "none", timeout=ctx.timeout,
                    max_retries=0, default_headers=ctx.target.headers or None)
    try:
        with client.chat.completions.stream(
            model=body["model"], messages=body["messages"], tools=body["tools"], temperature=0
        ) as stream:
            final = stream.get_final_completion()
    except Exception as err:  # noqa: BLE001 - any SDK failure is the finding
        res.reason = f"{type(err).__name__}: {err}"[:300]
        if isinstance(err, APIConnectionError):  # includes APITimeoutError: not a verdict on the stream format
            res.grade = ERROR
        # fetch the raw stream too: it is evidence, and tells whether a missing `index` is the cause
        raw = ctx.get("stream")
        res.scenarios = ["stream"]
        chunks = parse_sse(raw.sse_lines).chunks
        if chunks and assemble(chunks).missing_index:
            res.reason += " (the raw stream has delta.tool_calls entries without `index`; the SDK needs it to merge fragments)"
        res.info = {"exception": type(err).__name__}
        return res
    finally:
        client.close()
    message = final.choices[0].message if final.choices else None
    calls = (message.tool_calls or []) if message else []
    res.info = {"tool_calls": len(calls), "finish_reason": final.choices[0].finish_reason if final.choices else None}
    if not calls:
        res.reason = "SDK assembled the stream without tool_calls"
    else:
        res.grade = PASS
    return res
