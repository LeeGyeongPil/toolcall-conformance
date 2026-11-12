"""Command line interface: demo, run, mock, list."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import NoReturn

from . import __version__, i18n
from .checks import CheckSpec, all_checks
from .client import ConnectError
from .i18n import t
from .mock import MODES, MockServer
from .report import has_failures, render
from .runner import run_targets
from .targets import Target, TargetsError, _err, load_targets, make_target

EXIT_OK, EXIT_FAIL, EXIT_USAGE = 0, 1, 2


def _preparse_lang(argv: list[str]) -> str:
    """Decide the screen language before the real parser exists, so its help and errors are localized.

    Order: --lang (anywhere in argv) > TOOLCALL_CONFORMANCE_LANG > LC_ALL/LC_MESSAGES/LANG > en.
    An unsupported --lang value is left for the real parser to reject (usage error, exit 2).
    """
    class _Quiet(argparse.ArgumentParser):
        def error(self, message: str) -> NoReturn:  # stay silent; the real parser reports it once
            raise SystemExit(EXIT_USAGE)

    pre = _Quiet(add_help=False, allow_abbrev=False)
    pre.add_argument("--lang")
    try:
        known, _rest = pre.parse_known_args(argv)
    except SystemExit:  # e.g. a trailing "--lang" with no value; the real parser reports it
        return i18n.detect()
    return known.lang if known.lang in i18n.LANGS else i18n.detect()


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="toolcall-conformance", description=t("prog.description"))
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--lang", choices=list(i18n.LANGS), help=t("help.lang"))
    sub = p.add_subparsers(dest="command", required=True)

    def lang_option(sp: argparse.ArgumentParser) -> None:
        # Also accepted after the subcommand; SUPPRESS keeps a value given before it.
        sp.add_argument("--lang", choices=list(i18n.LANGS), default=argparse.SUPPRESS, help=t("help.lang"))

    def common(sp: argparse.ArgumentParser) -> None:
        lang_option(sp)
        sp.add_argument("--format", choices=["text", "md", "json"], default="text", help=t("help.format"))
        sp.add_argument("--timeout", type=float, default=180.0, help=t("help.timeout"))

    d = sub.add_parser("demo", help=t("help.demo"))
    common(d)

    r = sub.add_parser("run", help=t("help.run"))
    common(r)
    r.add_argument("--base-url", help=t("help.base_url"))
    r.add_argument("--model", help=t("help.model"))
    r.add_argument("--name", help=t("help.name"))
    r.add_argument("--targets", help=t("help.targets"))
    r.add_argument("--api-key-env", default="", help=t("help.api_key_env"))
    r.add_argument("--only", help=t("help.only"))
    r.add_argument("--out", help=t("help.out"))
    r.add_argument("--resume", action="store_true", help=t("help.resume"))

    m = sub.add_parser("mock", help=t("help.mock"))
    lang_option(m)
    m.add_argument("--host", default="127.0.0.1", help=t("help.host"))
    m.add_argument("--port", type=int, default=8089, help=t("help.port"))

    ls = sub.add_parser("list", help=t("help.list"))
    lang_option(ls)
    return p


def _select_checks(only: str | None) -> list[CheckSpec]:
    checks = all_checks()
    if only is None:
        return checks
    wanted = [x.strip() for x in only.split(",") if x.strip()]
    known = {c.id for c in checks}
    if not wanted:
        # Empty value, commas or spaces only (e.g. an unset CI variable): refuse instead of running nothing.
        raise _err("only_empty", only=only, valid=", ".join(sorted(known)))
    unknown = [w for w in wanted if w not in known]
    if unknown:
        raise _err("only_unknown", unknown=", ".join(unknown), valid=", ".join(sorted(known)))
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
        print(t("demo.timing", seconds=f"{time.monotonic() - started:.1f}", modes=", ".join(MODES)))
    good = next(tr for tr in results if tr.target.name == "good")
    return EXIT_FAIL if has_failures([good]) else EXIT_OK


def _cmd_run(args: argparse.Namespace) -> int:
    if args.targets and (args.base_url or args.model):
        raise _err("targets_xor")
    if args.targets:
        targets = load_targets(args.targets)
    elif args.base_url and args.model:
        targets = [make_target(args.name or args.base_url, args.base_url, args.model, args.api_key_env)]
    else:
        raise _err("need_target")
    if args.resume and not args.out:
        raise _err("resume_needs_out")
    checks = _select_checks(args.only)
    results = run_targets(
        targets, checks, timeout=args.timeout, out_path=_out_path(args.out), resume=args.resume,
        progress=(lambda m: print(t("run.progress", item=m), file=sys.stderr)) if args.format == "text" else None,
        skip_unreachable=bool(args.targets))
    skipped = [tr for tr in results if tr.skipped]
    for tr in skipped:  # stderr only: stdout stays clean JSON/Markdown
        hint = "" if tr.target.unavailable else t("run.skip_hint")
        err = tr.target.unavailable_error
        reason = t(f"err.{err.code}", **err.params) if err and err.code else tr.skipped
        print(t("run.skipping", name=tr.target.name, reason=reason, hint=hint), file=sys.stderr)
    if skipped and len(skipped) == len(results):
        return EXIT_USAGE  # every target was skipped: nothing was checked
    print(render(results, checks, args.format))
    return EXIT_FAIL if has_failures(results) else EXIT_OK


def _cmd_mock(args: argparse.Namespace) -> int:
    with MockServer(args.host, args.port) as srv:
        print(t("mock.header"))
        for mode, fault in MODES.items():
            print(f"  {srv.url(mode)}   # {mode}: {i18n.mode_description(mode, fault.description)}")
        print(t("mock.stop"))
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            print()
    return EXIT_OK


def _cmd_list(_args: argparse.Namespace) -> int:
    print(t("list.checks"))
    for c in all_checks():
        print(f"  {c.id:<22} {i18n.check_summary(c.id, c.summary)}")
    print("\n" + t("list.modes"))
    for mode, fault in MODES.items():
        print(f"  {mode:<20} {i18n.mode_description(mode, fault.description)}  [{fault.source}]")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    i18n.set_lang(_preparse_lang(argv))
    # argparse builds some messages itself ("usage:", "error:", ...); route them through our table.
    original_gettext = argparse._
    argparse._ = i18n.argparse_gettext
    try:
        args = _parser().parse_args(argv)
    finally:
        argparse._ = original_gettext
    if getattr(args, "lang", None):
        i18n.set_lang(args.lang)
    handlers = {"demo": _cmd_demo, "run": _cmd_run, "mock": _cmd_mock, "list": _cmd_list}
    try:
        return handlers[args.command](args)
    except ConnectError as err:
        print(t("connect_error", message=err), file=sys.stderr)
        return EXIT_USAGE
    except TargetsError as err:
        message = t(f"err.{err.code}", **err.params) if err.code else str(err)
        print(t("error", message=message), file=sys.stderr)
        return EXIT_USAGE
    except OSError as err:
        print(t("error", message=err), file=sys.stderr)
        return EXIT_USAGE
    except KeyboardInterrupt:
        print(t("interrupted"), file=sys.stderr)
        return 130
