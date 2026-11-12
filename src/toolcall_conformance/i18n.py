"""Screen-language support (English / Korean) for the command line interface.

All user-facing strings live in ``MESSAGES`` below. Per-check ``reason`` strings are evidence data
(written to JSON/JSONL) and are intentionally NOT translated.
"""

from __future__ import annotations

import os
from typing import Any

LANGS = ("en", "ko")
ENV_VAR = "TOOLCALL_CONFORMANCE_LANG"

_lang: str | None = None


def normalize(value: str | None) -> str | None:
    """Map a locale-like value ("ko_KR.UTF-8", "en", ...) to "en" or "ko"; None if empty."""
    if not value:
        return None
    return "ko" if value.strip().lower().startswith("ko") else "en"


def detect(env: dict[str, str] | None = None) -> str:
    """Language from TOOLCALL_CONFORMANCE_LANG, then LC_ALL, LC_MESSAGES, LANG; default English."""
    env = os.environ if env is None else env
    for name in (ENV_VAR, "LC_ALL", "LC_MESSAGES", "LANG"):
        found = normalize(env.get(name))
        if found:
            return found
    return "en"


def set_lang(lang: str | None) -> None:
    """Set the current language ("en"/"ko"); None goes back to automatic detection."""
    global _lang
    if lang is not None and lang not in LANGS:
        raise ValueError(f"unsupported language {lang!r}; use one of {', '.join(LANGS)}")
    _lang = lang


def get_lang() -> str:
    return _lang or detect()


def t(key: str, lang: str | None = None, **params: Any) -> str:
    """Look up a message and fill its placeholders."""
    table = MESSAGES[lang or get_lang()]
    return table[key].format(**params) if params else table[key]


# Messages argparse builds itself (msgid -> Korean). Unknown ids fall through unchanged.
ARGPARSE_KO = {
    "usage: ": "사용법: ",
    "%(prog)s: error: %(message)s\n": "%(prog)s: 오류: %(message)s\n",
    "options": "옵션",
    "optional arguments": "옵션",
    "positional arguments": "위치 인자",
    "show this help message and exit": "도움말을 표시하고 종료합니다",
    "show program's version number and exit": "버전을 표시하고 종료합니다",
    "the following arguments are required: %s": "다음 인자가 필요합니다: %s",
    "invalid choice: %(value)r (choose from %(choices)s)": "잘못된 선택입니다: %(value)r (선택 가능: %(choices)s)",
    "invalid choice: %(value)r (choose from: %(choices)s)": "잘못된 선택입니다: %(value)r (선택 가능: %(choices)s)",
    "argument %(argument_name)s: %(message)s": "인자 %(argument_name)s: %(message)s",
    "expected one argument": "값이 하나 필요합니다",
    "expected at least one argument": "값이 하나 이상 필요합니다",
    "unrecognized arguments: %s": "알 수 없는 인자: %s",
    "invalid %(type)s value: %(value)r": "%(type)s 값이 올바르지 않습니다: %(value)r",
    "ignored explicit argument %r": "무시된 명시적 인자: %r",
}


def argparse_gettext(msgid: str) -> str:
    """Drop-in for argparse's gettext function; translates when the current language is Korean."""
    if get_lang() == "ko":
        return ARGPARSE_KO.get(msgid, msgid)
    return msgid


MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        "prog.description": "Check how OpenAI-compatible servers handle tool calls on the wire.",
        "help.lang": "screen language: en or ko (default: TOOLCALL_CONFORMANCE_LANG, then LC_ALL/LC_MESSAGES/LANG, else en)",
        "help.format": "output format (default: text)",
        "help.timeout": "seconds per request (default: 180; slow local models need it)",
        "help.demo": "run every check against every built-in mock mode (no key, no GPU)",
        "help.run": "check a real server (or several, with --targets)",
        "help.base_url": "e.g. http://localhost:11434/v1",
        "help.model": "model name as the server knows it",
        "help.name": "label used in the table (default: the base URL)",
        "help.targets": "TOML file with [[target]] tables (see examples/targets.toml)",
        "help.api_key_env": "NAME of an environment variable holding the API key (the value is never recorded)",
        "help.only": "comma-separated check ids (see `list`); at least one id is required",
        "help.out": "write JSONL evidence here (a directory gets results.jsonl; or a .jsonl path)",
        "help.resume": "with --out: skip (target, check) pairs already recorded",
        "help.mock": "serve the mock deviation modes until Ctrl-C",
        "help.host": "address to bind (default: 127.0.0.1)",
        "help.port": "port to listen on (default: 8089)",
        "help.list": "describe the checks and mock modes",
        "error": "error: {message}",
        "connect_error": "error: {message}. Is the server running and is the base URL right?",
        "interrupted": "interrupted; finished checks are kept in the --out file (use --resume)",
        "list.checks": "Checks:",
        "list.modes": "Mock modes:",
        "mock.header": "Mock server (practice only) - base URLs:",
        "mock.stop": "Press Ctrl-C to stop.",
        "demo.timing": "({seconds}s; mock modes: {modes})",
        "run.progress": "  running {item}",
        "run.skipping": "skipping target {name}: {reason}{hint}",
        "run.skip_hint": ". Is the server running and is the base URL right?",
        "report.banner": "[mock] Practice results from the built-in mock server - not results from a real server.",
        "report.target": "target",
        "report.details": "Details (non-PASS)",
        "report.summary": "Summary",
        "report.columns": "Columns",
        # errors carried by TargetsError (code -> message)
        "err.only_empty": "--only has no check ids (got {only!r}). Valid ids: {valid}",
        "err.only_unknown": "unknown check id(s): {unknown}. Valid ids: {valid}",
        "err.targets_xor": "use either --targets or --base-url/--model, not both",
        "err.need_target": "give --base-url and --model, or --targets FILE",
        "err.resume_needs_out": "--resume needs --out (the JSONL file to continue)",
        "err.url_scheme": "{where}: base URL {url!r} must start with http:// or https:// (example: http://localhost:11434/v1)",
        "err.url_scheme_target": "target {name!r}: base URL {url!r} must start with http:// or https:// (example: http://localhost:11434/v1)",
        "err.model_empty": "target {name!r}: model must not be empty (pass --model or set `model`)",
        "err.key_unset": ("target {name!r}: environment variable {env} is not set. "
                          "Export it (export {env}=...) or drop api_key_env for servers without auth."),
        "err.file_missing": "targets file not found: {path}",
        "err.toml_invalid": "{path}: invalid TOML: {detail}",
        "err.no_targets": "{path}: add at least one [[target]] table with name, base_url and model",
        "err.target_field": "{path}: [[target]] #{index} needs a non-empty string `{key}`",
        "err.target_dup": "{path}: duplicate target name {name!r}",
        "err.headers_type": "{path}: target {name!r}: `headers` must be a table of strings",
        # check summaries (id -> text)
        "check.nonstream_basic": "Non-stream message.tool_calls (id, type, name, arguments string) and finish_reason",
        "check.content_leak": "Tool call text leaking into content (thinking-token fields are ignored)",
        "check.args_schema": "arguments parse as JSON and satisfy the tool schema (required, basic types)",
        "check.stream_assembly": "Streamed delta.tool_calls assemble by index; id/name present; finish_reason",
        "check.stream_terminator": "Stream ends with `data: [DONE]`",
        "check.sdk_stream_compat": "The official openai SDK stream helper assembles the same request without error",
        "check.tool_choice_none": 'tool_choice "none" suppresses tool calls even when the prompt invites one',
        "check.tool_choice_required": 'tool_choice "required" forces a call when the prompt needs no tool',
        "check.tool_choice_named": "tool_choice naming a function forces that function",
        "check.parallel_calls": "Two independent requests produce two tool_calls in one turn (WARN if only one)",
        "check.roundtrip": "assistant tool_calls + tool message (tool_call_id) accepted; final answer with stop",
        # mock mode descriptions (name -> text)
        "mode.good": "No deviation; arguments are split into several fragments.",
        "mode.no_index": "Streamed tool_calls[] entries have no `index`.",
        "mode.content_leak": "<tool_call>{{...}}</tool_call> text in content, finish_reason stop.",
        "mode.empty_stop": "Empty content and finish_reason stop.",
        "mode.whole_args": "Whole tool call in one streamed chunk.",
        "mode.tool_choice_ignored": "tool_choice is ignored.",
        "mode.bad_json_args": "Arguments JSON is truncated.",
        "mode.no_done": "Stream ends without `data: [DONE]`.",
        "mode.ollama_like": "whole_args + tool_choice_ignored + reasoning field + extra index.",
    },
    "ko": {
        "prog.description": "OpenAI 호환 서버가 도구 호출을 전송 형식 수준에서 어떻게 처리하는지 점검합니다.",
        "help.lang": "화면 언어: en 또는 ko (기본값: TOOLCALL_CONFORMANCE_LANG, 다음 LC_ALL/LC_MESSAGES/LANG, 그 외 en)",
        "help.format": "출력 형식 (기본값: text)",
        "help.timeout": "요청당 제한 시간(초) (기본값: 180, 느린 로컬 모델에 필요합니다)",
        "help.demo": "내장 목(mock) 모드 전체에 모든 검사를 실행합니다 (키와 GPU가 필요 없습니다)",
        "help.run": "실제 서버를 점검합니다 (--targets 로 여러 서버도 가능합니다)",
        "help.base_url": "예: http://localhost:11434/v1",
        "help.model": "서버에서 쓰는 모델 이름",
        "help.name": "표에 쓸 이름 (기본값: 기본 URL)",
        "help.targets": "[[target]] 표가 들어 있는 TOML 파일 (examples/targets.toml 참고)",
        "help.api_key_env": "API 키가 들어 있는 환경 변수의 이름 (값은 기록하지 않습니다)",
        "help.only": "쉼표로 구분한 검사 ID (`list` 참고), 하나 이상 필요합니다",
        "help.out": "JSONL 증거를 이곳에 기록합니다 (디렉터리면 results.jsonl 생성, 또는 .jsonl 경로)",
        "help.resume": "--out 과 함께 사용: 이미 기록된 (대상, 검사) 쌍은 건너뜁니다",
        "help.mock": "Ctrl-C 를 누를 때까지 목 편차 모드를 제공합니다",
        "help.host": "바인딩할 주소 (기본값: 127.0.0.1)",
        "help.port": "수신 포트 (기본값: 8089)",
        "help.list": "검사와 목 모드를 설명합니다",
        "error": "오류: {message}",
        "connect_error": "오류: {message}. 서버가 실행 중인지, 기본 URL이 올바른지 확인하십시오.",
        "interrupted": "중단되었습니다. 끝난 검사는 --out 파일에 남아 있습니다 (--resume 으로 이어 실행하십시오).",
        "list.checks": "검사:",
        "list.modes": "목 모드:",
        "mock.header": "목 서버 (연습용) - 기본 URL:",
        "mock.stop": "중지하려면 Ctrl-C 를 누르십시오.",
        "demo.timing": "({seconds}초, 목 모드: {modes})",
        "run.progress": "  실행 중: {item}",
        "run.skipping": "대상 건너뜀 {name}: {reason}{hint}",
        "run.skip_hint": ". 서버가 실행 중인지, 기본 URL이 올바른지 확인하십시오.",
        "report.banner": "[mock] 내장 목(mock) 서버의 연습용 결과입니다. 실제 서버의 결과가 아닙니다.",
        "report.target": "대상",
        "report.details": "상세 (PASS 제외)",
        "report.summary": "요약",
        "report.columns": "열",
        "err.only_empty": "--only 에 검사 ID가 없습니다 (입력값: {only!r}). 사용 가능한 ID: {valid}",
        "err.only_unknown": "알 수 없는 검사 ID: {unknown}. 사용 가능한 ID: {valid}",
        "err.targets_xor": "--targets 와 --base-url/--model 중 하나만 사용하십시오",
        "err.need_target": "--base-url 과 --model 을 함께 지정하거나 --targets 파일을 지정하십시오",
        "err.resume_needs_out": "--resume 에는 --out 이 필요합니다 (이어서 실행할 JSONL 파일)",
        "err.url_scheme": "{where}: 기본 URL은 http:// 또는 https:// 로 시작해야 합니다 (입력값: {url!r}, 예: http://localhost:11434/v1)",
        "err.url_scheme_target": "대상 {name!r}: 기본 URL은 http:// 또는 https:// 로 시작해야 합니다 (입력값: {url!r}, 예: http://localhost:11434/v1)",
        "err.model_empty": "대상 {name!r}: 모델 이름이 비어 있습니다 (--model 을 지정하거나 `model` 을 설정하십시오)",
        "err.key_unset": ("대상 {name!r}: 환경 변수가 설정되지 않았습니다: {env}. "
                          "export {env}=... 로 설정하거나, 인증이 없는 서버라면 api_key_env 를 제거하십시오."),
        "err.file_missing": "대상 파일을 찾을 수 없습니다: {path}",
        "err.toml_invalid": "{path}: TOML 형식이 올바르지 않습니다: {detail}",
        "err.no_targets": "{path}: name, base_url, model 이 있는 [[target]] 표를 하나 이상 추가하십시오",
        "err.target_field": "{path}: [[target]] {index}번째 항목에 비어 있지 않은 문자열 항목이 필요합니다: `{key}`",
        "err.target_dup": "{path}: 대상 이름이 중복되었습니다: {name!r}",
        "err.headers_type": "{path}: 대상 {name!r}: `headers` 는 문자열 표여야 합니다",
        "check.nonstream_basic": "비스트리밍 message.tool_calls (id, type, name, arguments 문자열)와 finish_reason",
        "check.content_leak": "도구 호출 텍스트가 content 로 새는지 (사고 토큰 필드는 무시)",
        "check.args_schema": "arguments 가 JSON 으로 파싱되고 도구 스키마(필수 항목, 기본 타입)를 만족하는지",
        "check.stream_assembly": "스트리밍 delta.tool_calls 가 index 기준으로 조립되는지, id/name 존재, finish_reason",
        "check.stream_terminator": "스트림이 `data: [DONE]` 으로 끝나는지",
        "check.sdk_stream_compat": "공식 openai SDK 스트림 헬퍼가 같은 요청을 오류 없이 조립하는지",
        "check.tool_choice_none": 'tool_choice "none" 이 프롬프트가 도구를 유도해도 도구 호출을 막는지',
        "check.tool_choice_required": 'tool_choice "required" 가 도구가 필요 없는 프롬프트에서도 호출을 강제하는지',
        "check.tool_choice_named": "함수를 지정한 tool_choice 가 그 함수 호출을 강제하는지",
        "check.parallel_calls": "독립된 두 요청이 한 턴에 tool_calls 두 개를 만드는지 (하나뿐이면 WARN)",
        "check.roundtrip": "assistant tool_calls + tool 메시지(tool_call_id)가 수락되고 stop 으로 최종 답변이 나오는지",
        "mode.good": "편차 없음. arguments 가 여러 조각으로 나뉩니다.",
        "mode.no_index": "스트리밍 tool_calls[] 항목에 `index` 가 없습니다.",
        "mode.content_leak": "content 에 <tool_call>{{...}}</tool_call> 텍스트가 있고 finish_reason 은 stop 입니다.",
        "mode.empty_stop": "content 가 비어 있고 finish_reason 은 stop 입니다.",
        "mode.whole_args": "도구 호출 전체가 스트림 청크 하나에 담깁니다.",
        "mode.tool_choice_ignored": "tool_choice 가 무시됩니다.",
        "mode.bad_json_args": "arguments JSON 이 잘려 있습니다.",
        "mode.no_done": "스트림이 `data: [DONE]` 없이 끝납니다.",
        "mode.ollama_like": "whole_args + tool_choice_ignored + reasoning 필드 + 추가 index.",
    },
}


def check_summary(check_id: str, fallback: str, lang: str | None = None) -> str:
    return MESSAGES[lang or get_lang()].get(f"check.{check_id}", fallback)


def mode_description(mode: str, fallback: str, lang: str | None = None) -> str:
    text = MESSAGES[lang or get_lang()].get(f"mode.{mode}")
    return text.format() if text else fallback
