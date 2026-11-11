"""Command line interface: demo, run, mock, list."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from . import __version__
from .checks import CheckSpec, all_checks
from .client import ConnectError
from .mock import MODES, MockServer
from .report import has_failures, render
from .runner import run_targets
from .targets import Target, TargetsError, load_targets, make_target

EXIT_OK, EXIT_FAIL, EXIT_USAGE = 0, 1, 2


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="toolcall-conformance",
        description="Check how OpenAI-compatible servers handle tool calls on the wire.")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--format", choices=["text", "md", "json"], default="text", help="output format (default: text)")
        sp.add_argument("--timeout", type=float, default=180.0, help="seconds per request (default: 180; slow local models need it)")

    d = sub.add_parser("demo", help="run every check against every built-in mock mode (no key, no GPU)")
    common(d)

    r = sub.add_parser("run", help="check a real server (or several, with --targets)")
    common(r)
    r.add_argument("--base-url", help="e.g. http://localhost:11434/v1")
    r.add_argument("--model", help="model name as the server knows it")
    r.add_argument("--name", help="label used in the table (default: the base URL)")
    r.add_argument("--targets", help="TOML file with [[target]] tables (see examples/targets.toml)")
    r.add_argument("--api-key-env", default="", help="NAME of an environment variable holding the API key (the value is never recorded)")
    r.add_argument("--only", help="comma-separated check ids (see `list`); at least one id is required")
    r.add_argument("--out", help="write JSONL evidence here (a directory gets results.jsonl; or a .jsonl path)")
    r.add_argument("--resume", action="store_true", help="with --out: skip (target, check) pairs already recorded")

    m = sub.add_parser("mock", help="serve the mock deviation modes until Ctrl-C")
    m.add_argument("--host", default="127.0.0.1")
    m.add_argument("--port", type=int, default=8089)

    sub.add_parser("list", help="describe the checks and mock modes")
    return p


def _select_checks(only: str | None) -> list[CheckSpec]:
    checks = all_checks()
    if only is None:
        return checks
    wanted = [x.strip() for x in only.split(",") if x.strip()]
    known = {c.id for c in checks}
    if not wanted:
        # Empty value, commas or spaces only (e.g. an unset CI variable): refuse instead of running nothing.
        raise TargetsError(f"--only has no check ids (got {only!r}). Valid ids: {', '.join(sorted(known))}")
    unknown = [w for w in wanted if w not in known]
    if unknown:
        raise TargetsError(f"unknown check id(s): {', '.join(unknown)}. Valid ids: {', '.join(sorted(known))}")
    return [c for c in checks if c.id in wanted]


def _out_path(out: str | None) -> Path | None:
    if not out:
        return None
    p = Path(out)
    return p if p.suffix == ".jsonl" else p / "results.jsonl"


def _cmd_demo(args: argparse.Namespace) -> int:
    checks = all_checks()
    started = time.monotonic()
    with MockServer() as srv:
        targets = [Target(name=mode, base_url=srv.url(mode), model="mock") for mode in MODES]
        results = run_targets(targets, checks, timeout=args.timeout)
    print(render(results, checks, args.format))
    if args.format == "text":
        print(f"({time.monotonic() - started:.1f}s; mock modes: {', '.join(MODES)})")
    good = next(tr for tr in results if tr.target.name == "good")
    return EXIT_FAIL if has_failures([good]) else EXIT_OK


def _cmd_run(args: argparse.Namespace) -> int:
    if args.targets and (args.base_url or args.model):
        raise TargetsError("use either --targets or --base-url/--model, not both")
    if args.targets:
        targets = load_targets(args.targets)
    elif args.base_url and args.model:
        targets = [make_target(args.name or args.base_url, args.base_url, args.model, args.api_key_env)]
    else:
        raise TargetsError("give --base-url and --model, or --targets FILE")
    if args.resume and not args.out:
        raise TargetsError("--resume needs --out (the JSONL file to continue)")
    checks = _select_checks(args.only)
    results = run_targets(
        targets, checks, timeout=args.timeout, out_path=_out_path(args.out), resume=args.resume,
        progress=(lambda m: print(f"  running {m}", file=sys.stderr)) if args.format == "text" else None)
    print(render(results, checks, args.format))
    return EXIT_FAIL if has_failures(results) else EXIT_OK


def _cmd_mock(args: argparse.Namespace) -> int:
    with MockServer(args.host, args.port) as srv:
        print("Mock server (practice only) - base URLs:")
        for mode, fault in MODES.items():
            print(f"  {srv.url(mode)}   # {mode}: {fault.description}")
        print("Press Ctrl-C to stop.")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            print()
    return EXIT_OK


def _cmd_list(_args: argparse.Namespace) -> int:
    print("Checks:")
    for c in all_checks():
        print(f"  {c.id:<22} {c.summary}")
    print("\nMock modes:")
    for mode, fault in MODES.items():
        print(f"  {mode:<20} {fault.description}  [{fault.source}]")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    handlers = {"demo": _cmd_demo, "run": _cmd_run, "mock": _cmd_mock, "list": _cmd_list}
    try:
        return handlers[args.command](args)
    except ConnectError as err:
        print(f"error: {err}. Is the server running and is the base URL right?", file=sys.stderr)
        return EXIT_USAGE
    except (TargetsError, OSError) as err:
        print(f"error: {err}", file=sys.stderr)
        return EXIT_USAGE
    except KeyboardInterrupt:
        print("interrupted; finished checks are kept in the --out file (use --resume)", file=sys.stderr)
        return 130
