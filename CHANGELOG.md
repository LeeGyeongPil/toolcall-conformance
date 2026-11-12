# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [0.3.0] - 2026-11-13

### Added
- Screen language selection, English and Korean: `--lang en|ko` (accepted before or after the subcommand), then the `TOOLCALL_CONFORMANCE_LANG` environment variable, then `LC_ALL`/`LC_MESSAGES`/`LANG` (a value starting with `ko` selects Korean; anything else, English). It covers `--help`, argparse usage errors, error messages, `list`, `mock`, progress lines and the text/Markdown report labels. Messages live in `toolcall_conformance/i18n.py`.
- `TargetsError` now carries `code` and `params`; `str(err)` is unchanged (English).
- `render`, `render_text`, `render_markdown` accept an optional `lang` keyword.

### Changed
- The mock banner of text/Markdown output is now a single line in the selected language (it used to contain English and Korean together). Scripts that match the banner text should match the English sentence `[mock] Practice results from the built-in mock server - not results from a real server.` (its trailing space and Korean part are gone).
- With a Korean locale (for example `LANG=ko_KR.UTF-8`) text output is now Korean by default; set `TOOLCALL_CONFORMANCE_LANG=en` or pass `--lang en` to keep English.

### Unchanged
- `--format json` output, JSONL evidence, per-check `reason` strings, check ids, grade tokens and exit codes do not depend on the language.

## [0.2.0] - 2026-11-12

### Changed
- `run --targets` now skips a target that refuses the connection, fails DNS, or whose `api_key_env` variable is unset: it is recorded as `ERROR` rows (reason `target skipped: ...`, also in the JSONL) and the remaining targets are still checked. A line `skipping target <name>: <reason>` is printed to stderr. Exit code 2 is now used only when every target was skipped. Behavior change for CI: a run that used to exit 2 because one target was down now exits 1. A single `--base-url` run is unchanged. `run_targets(..., skip_unreachable=True)` enables this for library callers (default unchanged). With `--resume`, results already recorded for a skipped target are kept; only unrecorded checks become `ERROR`. This resolves the 0.1.0 known limitation about unreachable targets.

## [0.1.2] - 2026-11-11

### Fixed
- `run --only` with no check ids (an empty value, commas or spaces only, e.g. an unset CI variable) now fails with `error: --only has no check ids (...)` and exit code 2 instead of running zero checks and exiting 0 with an empty table. This resolves the 0.1.0 limitation about `--only ','`. Omitting `--only` still runs all 11 checks. Behavior change: `--only ''` used to run all checks; it is now a usage error.

### Documentation
- README: the `--only` row and the troubleshooting table now also cover unknown check ids (`error: unknown check id(s)`, exit code 2).

## [0.1.1] - 2026-11-11

### Fixed
- Timeouts and broken connections (`Exchange.error`, and the SDK's `APIConnectionError`/`APITimeoutError`) are now graded `ERROR` instead of `FAIL`, as documented. A slow server no longer looks like a wire-format violation. `content_leak` and `args_schema` also report `ERROR` (not `SKIP`) when a transport problem is why they had nothing to inspect. HTTP error statuses are unchanged (`FAIL`, or `WARN` for 4xx on `tool_choice`/parallel). A connection that is reset after it was established now yields `ERROR` (exit code 1) instead of aborting with exit code 2; exit 2 remains for usage errors and for refused or unresolvable servers.
- `--resume` now re-runs pairs recorded as `ERROR` and appends the new result; `PASS`/`WARN`/`FAIL`/`SKIP` records are still skipped. This resolves the 0.1.0 limitation about `--resume` and `ERROR`.

### Known limitations
- If `nonstream_basic` succeeds but only the stream is cut off, the resulting `args_schema` `SKIP` is not re-run by `--resume`.
- Mid-transfer socket resets are covered by unit tests with a faked transport, not by a real-socket test.
- The demo mock server may print a BrokenPipe message on stderr when a client disconnects early.
- If every target refuses the connection the run stops; the "first server" wording in the README only describes the probing order.

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
