"""AC-1 and AC-7 .. AC-10, plus input-validation paths."""

import contextlib
import json
import socket
import struct
import threading
import time

import pytest

from toolcall_conformance.cli import main

SECRET = "sk-test-secret-value-123"


def run(capsys, *argv):
    code = main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


def test_demo_matrix(capsys):
    start = time.monotonic()
    code, out, _ = run(capsys, "demo")
    assert time.monotonic() - start < 10
    assert code == 0
    first = out.splitlines()[0]
    assert "mock" in first and "not results from a real server" in first
    rows = {line.split()[0]: line for line in out.splitlines() if line.split() and line.split()[0] in (
        "good", "no_index", "content_leak", "empty_stop", "whole_args", "tool_choice_ignored",
        "bad_json_args", "no_done", "ollama_like")}
    assert len(rows) == 9
    assert "FAIL" not in rows["good"] and "ERR" not in rows["good"]
    assert "FAIL" in rows["no_index"]


def test_run_jsonl_redaction_exit_codes(capsys, server, tmp_path, monkeypatch):
    monkeypatch.setenv("TOOLCALL_API_KEY", SECRET)
    out_dir = tmp_path / "runs"
    code, out, err = run(capsys, "run", "--base-url", server.url("no_index"), "--model", "mock",
                         "--out", str(out_dir), "--api-key-env", "TOOLCALL_API_KEY")
    assert code == 1
    lines = (out_dir / "results.jsonl").read_text().splitlines()
    assert len(lines) == 11
    rec = {json.loads(l)["check"]: json.loads(l) for l in lines}
    stream = rec["stream_assembly"]
    assert stream["target"]["mock"] is True and stream["grade"] == "FAIL" and stream["reason"]
    assert stream["evidence"][0]["request"]["stream"] is True
    assert any(l.startswith("data:") for l in stream["evidence"][0]["sse_lines"])
    assert rec["nonstream_basic"]["evidence"][0]["response"]
    assert rec["sdk_stream_compat"]["sdk_version"]
    assert SECRET not in (out_dir / "results.jsonl").read_text() + out + err
    code, *_ = run(capsys, "run", "--base-url", server.url("good"), "--model", "mock")
    assert code == 0


def test_targets_matrix_formats(capsys, server, tmp_path):
    toml = tmp_path / "t.toml"
    toml.write_text(
        f'[[target]]\nname = "direct-good"\nbase_url = "{server.url("good")}"\nmodel = "m"\n'
        f'[[target]]\nname = "proxy-leaky"\nbase_url = "{server.url("content_leak")}"\nmodel = "m"\nnotes = "x"\n')
    code, out, _ = run(capsys, "run", "--targets", str(toml), "--format", "md")
    header = next(l for l in out.splitlines() if l.startswith("| target"))
    assert code == 1 and "nonstream_basic" in header
    assert "| direct-good |" in out and "| proxy-leaky |" in out
    code, out, _ = run(capsys, "run", "--targets", str(toml), "--format", "json")
    data = json.loads(out)
    assert [t["name"] for t in data["targets"]] == ["direct-good", "proxy-leaky"] and data["failed"] is True
    code, out, _ = run(capsys, "run", "--targets", str(toml))
    assert "direct-good" in out and "proxy-leaky" in out


def test_resume_and_only(capsys, server, tmp_path):
    out_file = tmp_path / "r.jsonl"
    args = ["run", "--base-url", server.url("good"), "--model", "mock", "--out", str(out_file)]
    run(capsys, *args)
    assert len(out_file.read_text().splitlines()) == 11
    before = server.request_count
    code, *_ = run(capsys, *args, "--resume")
    assert code == 0 and server.request_count == before  # nothing re-requested
    assert len(out_file.read_text().splitlines()) == 11
    only_file = tmp_path / "only.jsonl"
    run(capsys, "run", "--base-url", server.url("good"), "--model", "mock", "--out", str(only_file),
        "--only", "roundtrip,stream_terminator")
    assert len(only_file.read_text().splitlines()) == 2


def test_resume_continues_a_partial_file(capsys, server, tmp_path):
    out_file = tmp_path / "p.jsonl"
    base = ["run", "--base-url", server.url("good"), "--model", "mock", "--out", str(out_file)]
    run(capsys, *base, "--only", "roundtrip")
    run(capsys, *base, "--resume")
    checks = [json.loads(l)["check"] for l in out_file.read_text().splitlines()]
    assert len(checks) == 11 and len(set(checks)) == 11


def test_unreachable_target_exit2(capsys):
    code, _, err = run(capsys, "run", "--base-url", "http://127.0.0.1:9/v1", "--model", "m")
    assert code == 2
    assert "cannot connect" in err and "Traceback" not in err


@pytest.mark.parametrize("argv, message", [
    (["run"], "--base-url and --model"),
    (["run", "--base-url", "localhost:11434", "--model", "m"], "http://"),
    (["run", "--base-url", "http://127.0.0.1:1/v1", "--model", "m", "--only", "nope"], "Valid ids"),
    (["run", "--base-url", "http://127.0.0.1:1/v1", "--model", "m", "--resume"], "--out"),
    (["run", "--base-url", "http://127.0.0.1:1/v1", "--model", "m", "--api-key-env", "NOT_SET_ANYWHERE"], "not set"),
    (["run", "--targets", "missing.toml"], "not found"),
])
def test_usage_errors_exit2_with_fix_hint(capsys, argv, message, monkeypatch):
    monkeypatch.delenv("NOT_SET_ANYWHERE", raising=False)
    code, _, err = run(capsys, *argv)
    assert code == 2 and message in err and "Traceback" not in err


@pytest.mark.parametrize("only", [",", "   ", " , ,", ""])
@pytest.mark.parametrize("fmt", ["text", "json", "md"])
def test_only_without_check_ids_exit2(capsys, only, fmt):
    """`--only` that names no check (empty, commas, spaces) is a usage error, not a silent empty pass."""
    code, out, err = run(capsys, "run", "--base-url", "http://127.0.0.1:1/v1", "--model", "m",
                         "--only", only, "--format", fmt)
    assert code == 2 and out == ""
    assert "--only has no check ids" in err and "Valid ids" in err and "Traceback" not in err


def test_only_mixed_valid_and_unknown_exit2(capsys):
    code, out, err = run(capsys, "run", "--base-url", "http://127.0.0.1:1/v1", "--model", "m",
                         "--only", "roundtrip,nope")
    assert code == 2 and out == "" and "unknown check id(s): nope" in err


def test_only_tolerates_spaces_and_extra_commas(capsys, server):
    code, out, _ = run(capsys, "run", "--base-url", server.url("good"), "--model", "mock",
                       "--only", "roundtrip, ,stream_terminator,", "--format", "json")
    assert code == 0
    assert sorted({r["check"] for t in json.loads(out)["targets"] for r in t["results"]}) == ["roundtrip", "stream_terminator"]


def test_list_command(capsys):
    code, out, _ = run(capsys, "list")
    assert code == 0 and "sdk_stream_compat" in out and "ollama_like" in out


def test_timeout_is_error_not_crash(capsys):
    """A server that accepts but never answers yields ERROR rows, not a traceback."""
    import socket
    import threading

    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(5)
    held = []
    stop = threading.Event()

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
        code, out, _ = run(capsys, "run", "--base-url", f"http://127.0.0.1:{srv.getsockname()[1]}/v1",
                           "--model", "m", "--timeout", "0.5", "--only", "nonstream_basic", "--format", "json")
    finally:
        stop.set()
        t.join(timeout=2)
        for c in held:
            c.close()
        srv.close()
    assert code == 1
    data = json.loads(out)
    assert data["failed"] is True
    first = data["targets"][0]["results"][0]
    assert "timed out" in first["reason"]
    assert first["grade"] == "ERROR"  # a slow server is not a spec violation


def _read_request(conn: socket.socket) -> None:
    """Read one HTTP request completely (headers + Content-Length body); the client may send in pieces."""
    conn.settimeout(5)
    buf = b""
    try:
        while b"\r\n\r\n" not in buf:
            chunk = conn.recv(65536)
            if not chunk:
                return
            buf += chunk
        head, _, body = buf.partition(b"\r\n\r\n")
        want = 0
        for line in head.split(b"\r\n"):
            if line.lower().startswith(b"content-length:"):
                want = int(line.split(b":", 1)[1])
        while len(body) < want:
            chunk = conn.recv(65536)
            if not chunk:
                return
            body += chunk
    except OSError:
        return


@contextlib.contextmanager
def _silent_server(reset: bool = False):
    """Loopback server on a free port: accepts, then stays silent (or resets the connection)."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(5)
    held: list[socket.socket] = []
    stop = threading.Event()

    def accept():
        srv.settimeout(0.2)
        while not stop.is_set():
            try:
                conn = srv.accept()[0]
            except OSError:
                continue
            if reset:
                _read_request(conn)  # take the whole request, then close with RST
                conn.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
                conn.close()
            else:
                held.append(conn)

    t = threading.Thread(target=accept, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{srv.getsockname()[1]}/v1"
    finally:
        stop.set()
        t.join(timeout=2)
        for c in held:
            c.close()
        srv.close()


def test_timeout_text_report_says_error(capsys):
    with _silent_server() as url:
        code, out, _ = run(capsys, "run", "--base-url", url, "--model", "m", "--timeout", "0.5",
                           "--only", "nonstream_basic")
    assert code == 1
    assert "ERR" in out and "nonstream_basic: ERROR: timed out after 0.5s" in out
    assert "Summary: ERROR=1" in out and "FAIL" not in out


def test_connection_reset_is_error(capsys):
    with _silent_server(reset=True) as url:
        code, out, _ = run(capsys, "run", "--base-url", url, "--model", "m", "--timeout", "2",
                           "--only", "nonstream_basic", "--format", "json")
    assert code == 1
    res = json.loads(out)["targets"][0]["results"][0]
    assert res["grade"] == "ERROR" and "transport error" in res["reason"]
