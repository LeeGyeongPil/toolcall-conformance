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


# --- transport problems are ERROR, HTTP/format problems stay FAIL ---------------------------

import json as _json

import pytest

from toolcall_conformance.checks import all_checks
from toolcall_conformance.client import Exchange
from toolcall_conformance.runner import run_targets
from toolcall_conformance.targets import Target

_HTTP_CHECKS = ["nonstream_basic", "stream_assembly", "stream_terminator", "tool_choice_none",
                "tool_choice_required", "tool_choice_named", "parallel_calls", "roundtrip"]


class _FakeContext:
    """Answers every scenario with the same canned Exchange (no network)."""

    def __init__(self, ex: Exchange) -> None:
        self._ex = ex

    def get(self, scenario: str) -> Exchange:
        return self._ex


def _check(check_id: str):
    return next(c for c in all_checks() if c.id == check_id)


@pytest.mark.parametrize("check_id", _HTTP_CHECKS + ["content_leak", "args_schema"])
def test_transport_error_grades_error(check_id):
    res = _check(check_id).fn(_FakeContext(Exchange("x", {}, error="timed out after 1s")))
    assert res.grade == "ERROR" and "timed out after 1s" in res.reason


@pytest.mark.parametrize("check_id", _HTTP_CHECKS)
def test_http_500_stays_fail(check_id):
    res = _check(check_id).fn(_FakeContext(Exchange("x", {}, status=500, text="oops")))
    assert res.grade == "FAIL" and "HTTP 500" in res.reason


@pytest.mark.parametrize("check_id", ["content_leak", "args_schema"])
def test_http_500_still_skips_text_checks(check_id):
    res = _check(check_id).fn(_FakeContext(Exchange("x", {}, status=500, text="oops")))
    assert res.grade == "SKIP"


def test_tool_choice_4xx_still_warns():
    res = _check("tool_choice_none").fn(_FakeContext(Exchange("x", {}, status=400, text="no")))
    assert res.grade == "WARN"


def test_sdk_timeout_grades_error():
    import socket
    import threading

    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(5)
    held, stop = [], threading.Event()

    def accept():
        srv.settimeout(0.2)
        while not stop.is_set():
            try:
                held.append(srv.accept()[0])
            except OSError:
                continue

    t = threading.Thread(target=accept, daemon=True)
    t.start()
    try:
        target = Target(name="slow", base_url=f"http://127.0.0.1:{srv.getsockname()[1]}/v1", model="m")
        results = run_targets([target], [_check("sdk_stream_compat")], timeout=0.5)
    finally:
        stop.set()
        t.join(timeout=2)
        for c in held:
            c.close()
        srv.close()
    res = results[0].results[0]
    assert res.grade == "ERROR" and res.info["exception"] == "APITimeoutError"


def test_resume_reruns_error_but_keeps_other_grades(server, tmp_path):
    out = tmp_path / "r.jsonl"
    target = Target(name="t", base_url=server.url("good"), model="mock")

    def line(check, grade):
        return _json.dumps({"target": {"name": "t", "mock": True}, "check": check, "grade": grade,
                            "reason": "earlier", "info": {}})

    out.write_text(line("nonstream_basic", "ERROR") + "\n" + line("roundtrip", "FAIL") + "\n", encoding="utf-8")
    specs = [_check("nonstream_basic"), _check("roundtrip")]
    before = server.request_count
    results = run_targets([target], specs, timeout=30, out_path=out, resume=True)
    by = {r.check: r for r in results[0].results}
    assert by["nonstream_basic"].grade == "PASS"
    assert by["roundtrip"].grade == "FAIL" and by["roundtrip"].reason == "earlier"
    assert server.request_count > before
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3 and _json.loads(lines[-1])["grade"] == "PASS"


@pytest.mark.parametrize("exc", [BrokenPipeError("pipe"), ConnectionResetError("reset")])
def test_drop_while_sending_is_transport_error(monkeypatch, exc):
    """Linux reports a peer reset while sending as URLError; it must still grade ERROR, not abort."""
    import urllib.error
    import urllib.request

    from toolcall_conformance import client

    def boom(*a, **k):
        raise urllib.error.URLError(exc)

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    ex = client.post_chat("http://127.0.0.1:9/v1", {}, "s", timeout=1)
    assert ex.error.startswith("transport error")
