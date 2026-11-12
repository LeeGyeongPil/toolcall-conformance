"""Render results as a terminal table, Markdown or JSON."""

from __future__ import annotations

import json
import unicodedata
from typing import Any

from .i18n import get_lang, t
from .checks import ERROR, FAIL, WARN, CheckSpec
from .runner import TargetResult


def banner(lang: str | None = None) -> str:
    """The mock-results notice, in one language (the selected one by default)."""
    return t("report.banner", lang)


BANNER = banner("en")  # kept for library callers


def _width(text: str) -> int:
    """Display width in terminal columns: wide and fullwidth characters (Hangul, CJK) take two."""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def _ljust(text: str, width: int) -> str:
    return text + " " * max(0, width - _width(text))


def has_failures(results: list[TargetResult]) -> bool:
    return any(r.grade in (FAIL, ERROR) for tr in results for r in tr.results)


def _is_mock(results: list[TargetResult]) -> bool:
    return any(tr.target.mock for tr in results)


def _cell(grade: str) -> str:
    return "ERR" if grade == ERROR else grade


def _details(results: list[TargetResult]) -> list[str]:
    lines = []
    for tr in results:
        for r in tr.results:
            extra = ""
            if r.info:
                extra = " [" + ", ".join(f"{k}={v}" for k, v in r.info.items() if v not in ([], "", None)) + "]"
            if r.grade != "PASS" and r.reason:
                lines.append(f"{tr.target.name} / {r.check}: {r.grade}: {r.reason}{extra}")
    return lines


def render_text(results: list[TargetResult], checks: list[CheckSpec], lang: str | None = None) -> str:
    lang = lang or get_lang()
    head = t("report.target", lang)
    name_w = max(6, _width(head), *(_width(tr.target.name) for tr in results))
    cols = [c.short for c in checks]
    widths = [max(_width(c), 4) for c in cols]
    lines = [banner(lang)] if _is_mock(results) else []
    lines.append(_ljust(head, name_w) + "  " + "  ".join(_ljust(c, w) for c, w in zip(cols, widths)))
    lines.append("-" * (name_w + sum(widths) + 2 * len(widths)))
    for tr in results:
        by_id = {r.check: r for r in tr.results}
        cells = [_ljust(_cell(by_id[c.id].grade) if c.id in by_id else "-", w) for c, w in zip(checks, widths)]
        lines.append(_ljust(tr.target.name, name_w) + "  " + "  ".join(cells))
    details = _details(results)
    if details:
        lines += ["", t("report.details", lang) + ":"] + [f"  {d}" for d in details]
    summary = {g: sum(r.grade == g for tr in results for r in tr.results) for g in ("PASS", WARN, FAIL, "SKIP", ERROR)}
    lines += ["", t("report.summary", lang) + ": " + ", ".join(f"{g}={n}" for g, n in summary.items() if n)]
    lines.append(t("report.columns", lang) + ": " + ", ".join(f"{c.short}={c.id}" for c in checks))
    return "\n".join(lines)


def render_markdown(results: list[TargetResult], checks: list[CheckSpec], lang: str | None = None) -> str:
    lang = lang or get_lang()
    lines = [f"> {banner(lang)}", ""] if _is_mock(results) else []
    lines.append(f"| {t('report.target', lang)} | " + " | ".join(c.id for c in checks) + " |")
    lines.append("|---|" + "---|" * len(checks))
    for tr in results:
        by_id = {r.check: r for r in tr.results}
        lines.append(f"| {tr.target.name} | " + " | ".join(_cell(by_id[c.id].grade) if c.id in by_id else "-" for c in checks) + " |")
    details = _details(results)
    if details:
        lines += ["", f"### {t('report.details', lang)}", ""] + [f"- {d}" for d in details]
    return "\n".join(lines)


def render_json(results: list[TargetResult]) -> str:
    payload: dict[str, Any] = {
        "mock": _is_mock(results),
        "failed": has_failures(results),
        "targets": [
            {"name": tr.target.name, "base_url": tr.target.base_url, "model": tr.target.model,
             "mock": tr.target.mock,
             "results": [{"check": r.check, "grade": r.grade, "reason": r.reason, "info": r.info,
                          "sdk_version": r.sdk_version or None} for r in tr.results]}
            for tr in results],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def render(results: list[TargetResult], checks: list[CheckSpec], fmt: str, lang: str | None = None) -> str:
    """Render in ``fmt`` (text, md, json). ``lang`` (en/ko) never affects JSON."""
    if fmt == "md":
        return render_markdown(results, checks, lang)
    if fmt == "json":
        return render_json(results)
    return render_text(results, checks, lang)
