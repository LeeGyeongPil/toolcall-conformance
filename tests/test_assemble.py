from toolcall_conformance.assemble import assemble
from toolcall_conformance.sse import parse_sse


def _chunk(delta, finish=None):
    return {"choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}


def test_parse_sse_skips_comments_and_flags_done():
    parsed = parse_sse([": keep-alive", "", 'data: {"a": 1}', "event: x", "data: not json", "data: [DONE]"])
    assert parsed.chunks == [{"a": 1}]
    assert parsed.done is True
    assert parsed.errors == ["not json"]


def test_parse_sse_without_done():
    assert parse_sse(['data: {"a": 1}']).done is False


def test_assemble_joins_fragments_by_index():
    chunks = [
        _chunk({"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "get_weather", "arguments": ""}}]}),
        _chunk({"tool_calls": [{"index": 1, "id": "c2", "function": {"name": "get_time", "arguments": "{}"}}]}),
        _chunk({"tool_calls": [{"index": 0, "function": {"arguments": '{"city":'}}]}),
        _chunk({"tool_calls": [{"index": 0, "function": {"arguments": '"Seoul"}'}}]}, "tool_calls"),
    ]
    asm = assemble(chunks)
    assert [(c.id, c.name, c.arguments) for c in asm.calls] == [
        ("c1", "get_weather", '{"city":"Seoul"}'), ("c2", "get_time", "{}")]
    assert asm.arg_fragments == 3
    assert asm.finish_reason == "tool_calls"
    assert asm.missing_index == []


def test_assemble_records_missing_index_and_repairability():
    chunks = [
        _chunk({"tool_calls": [{"id": "c1", "function": {"name": "get_weather", "arguments": ""}}]}),
        _chunk({"tool_calls": [{"function": {"arguments": '{"city":"Seoul"}'}}]}),
    ]
    asm = assemble(chunks)
    assert asm.missing_index == [0, 1]
    assert asm.calls == []
    assert asm.repairable is True


def test_assemble_separates_thinking_and_unknown_fields():
    asm = assemble([_chunk({"reasoning": "hm", "weird": 1, "content": "hi"})])
    assert asm.thinking_fields == ["reasoning"]
    assert asm.extra_fields == ["weird"]
    assert asm.content == "hi"
