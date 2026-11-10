import json
import urllib.error
import urllib.request

import pytest

from toolcall_conformance.client import MOCK_HEADER, post_chat
from toolcall_conformance.mock import MODES
from toolcall_conformance.scenarios import build_request
from toolcall_conformance.sse import parse_sse


def test_every_mode_has_a_route_and_marks_itself_mock(server):
    for mode in MODES:
        ex = post_chat(server.url(mode), build_request("basic", "m"), "basic", timeout=10)
        assert ex.status == 200 and ex.is_mock, mode


def test_unknown_mode_is_404_with_hint(server):
    base = server.url("good").replace("/mode/good", "/mode/nope")
    ex = post_chat(base, build_request("basic", "m"), "basic", timeout=10)
    assert ex.status == 404 and "known:" in ex.text


def test_bare_v1_path_serves_good_mode(server):
    base = server.url("good").replace("/mode/good", "")
    assert post_chat(base, build_request("basic", "m"), "basic", timeout=10).status == 200


def test_models_route(server):
    with urllib.request.urlopen(server.url("good") + "/models", timeout=10) as resp:
        assert json.load(resp)["data"][0]["id"] == "mock"
        assert resp.headers[MOCK_HEADER] == "1"


def test_good_stream_shape(server):
    ex = post_chat(server.url("good"), build_request("stream", "m"), "stream", timeout=10)
    parsed = parse_sse(ex.sse_lines)
    first = parsed.chunks[0]["choices"][0]["delta"]
    assert first.get("role") == "assistant" and "tool_calls" not in first  # role-only first chunk
    assert parsed.done


def test_no_index_mode_drops_index(server):
    ex = post_chat(server.url("no_index"), build_request("stream", "m"), "stream", timeout=10)
    entries = [tc for c in parse_sse(ex.sse_lines).chunks for tc in c["choices"][0]["delta"].get("tool_calls", [])]
    assert entries and all("index" not in tc for tc in entries)


def test_ollama_like_non_stream_has_extra_fields(server):
    msg = post_chat(server.url("ollama_like"), build_request("basic", "m"), "basic", timeout=10).json()["choices"][0]["message"]
    assert msg["reasoning"] and "index" in msg["tool_calls"][0]


def test_invalid_json_body_is_400(server):
    req = urllib.request.Request(server.url("good") + "/chat/completions", data=b"{oops", method="POST")
    with pytest.raises(urllib.error.HTTPError) as err:
        urllib.request.urlopen(req, timeout=10)
    assert err.value.code == 400


def test_request_counter_counts_chat_requests(server):
    before = server.request_count
    post_chat(server.url("good"), build_request("basic", "m"), "basic", timeout=10)
    assert server.request_count == before + 1


def test_unknown_mode_url_raises_helpful_error(server):
    with pytest.raises(ValueError, match="choose from"):
        server.url("nope")
