# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-11-10

### Added
- `demo`, `run`, `mock` and `list` commands.
- 11 checks: `nonstream_basic`, `content_leak`, `args_schema`, `stream_assembly`, `stream_terminator`,
  `sdk_stream_compat`, `tool_choice_none`, `tool_choice_required`, `tool_choice_named`, `parallel_calls`, `roundtrip`.
- Built-in mock server with 9 deviation modes served under `/mode/<mode>/v1`.
- Text, Markdown and JSON reports; JSONL evidence with `--resume` and `--only`; exit codes 0/1/2.
- `--targets` TOML files for server-by-model matrices.

### Known limitations
- `--only ','` (no valid names) prints an empty table and exits 0 instead of failing with exit code 2.
- `--resume` skips every recorded (target, check) pair, including ones recorded as `ERROR` (for example timeouts); rerun with a new `--out` to retry them.
- On `openai` 3.48.0 the `no_index` case fails inside the SDK with `TypeError` rather than `RuntimeError`; the verdict is the same.
- With `--targets`, an unreachable server aborts the whole run with exit code 2.
