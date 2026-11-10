"""Acceptance checks AC-2 .. AC-6: expected verdicts per mock mode."""

from toolcall_conformance.client import post_chat
from toolcall_conformance.scenarios import ROUNDTRIP_CALL_ID, build_request


def test_no_index_raw_vs_sdk(matrix):
    row = matrix["no_index"]
    assert row["nonstream_basic"].grade == "PASS"
    raw = row["stream_assembly"]
    assert raw.grade == "FAIL" and "missing index" in raw.reason
    assert raw.info["repairable"] is True
    sdk = row["sdk_stream_compat"]
    # the SDK refuses a stream the repairing raw assembler could still read
    assert sdk.grade == "FAIL" and "without `index`" in sdk.reason
    assert sdk.sdk_version


def test_content_leak_and_reasoning_separation(matrix):
    leak = matrix["content_leak"]
    assert leak["content_leak"].grade == "FAIL" and "<tool_call>" in leak["content_leak"].reason
    assert leak["nonstream_basic"].grade == "FAIL"
    assert matrix["good"]["content_leak"].grade == "PASS"
    # thinking tokens are present in ollama_like but must not count as a leak
    assert matrix["ollama_like"]["stream_assembly"].info["thinking_fields"] == ["reasoning"]
    assert matrix["ollama_like"]["content_leak"].grade == "PASS"


def test_tool_choice_checks(matrix):
    for mode in ("tool_choice_ignored", "ollama_like"):
        r = matrix[mode]["tool_choice_none"]
        assert r.grade == "FAIL" and "ignored" in r.reason
    for check in ("tool_choice_none", "tool_choice_required", "tool_choice_named"):
        assert matrix["good"][check].grade == "PASS", check


def test_stream_shape_variants(matrix):
    whole = matrix["whole_args"]["stream_assembly"]
    assert whole.grade == "PASS" and whole.info["arg_fragments"] == 1
    assert matrix["good"]["stream_assembly"].info["arg_fragments"] >= 2
    assert matrix["bad_json_args"]["args_schema"].grade == "FAIL"
    assert matrix["no_done"]["stream_terminator"].grade == "FAIL"
    assert matrix["good"]["stream_terminator"].grade == "PASS"


def test_roundtrip_parallel_empty_stop(matrix, server):
    good = matrix["good"]
    assert good["roundtrip"].grade == "PASS"
    assert good["parallel_calls"].grade == "PASS" and good["parallel_calls"].info["tool_calls"] == 2
    empty = matrix["empty_stop"]["nonstream_basic"]
    assert empty.grade == "FAIL" and "empty content with stop" in empty.reason
    # a tool message whose tool_call_id matches no assistant tool call is rejected with 400
    body = build_request("roundtrip", "m")
    body["messages"][-1]["tool_call_id"] = "call_other"
    assert ROUNDTRIP_CALL_ID != "call_other"
    ex = post_chat(server.url("good"), body, "roundtrip", timeout=10)
    assert ex.status == 400 and "tool_call_id" in ex.text


def test_good_row_has_no_problems(matrix):
    assert all(r.grade == "PASS" for r in matrix["good"].values())


def test_every_mode_has_all_eleven_checks(matrix):
    assert len(matrix) == 9
    assert all(len(row) == 11 for row in matrix.values())
