"""Render results as a terminal table, Markdown or JSON."""

from __future__ import annotations

import json
from typing import Any

from .checks import ERROR, FAIL, WARN, CheckSpec
from .runner import TargetResult

BANNER = ("[mock] Practice results from the built-in mock server - not results from a real server. "
          "(연습용 목(mock) 서버 결과입니다 - 실제 서버 결과가 아닙니다)")


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


def render_text(results: list[TargetResult], checks: list[CheckSpec]) -> str:
    name_w = max(6, *(len(tr.target.name) for tr in results))
    cols = [c.short for c in checks]
    widths = [max(len(c), 4) for c in cols]
    lines = [BANNER] if _is_mock(results) else []
    lines.append("target".ljust(name_w) + "  " + "  ".join(c.ljust(w) for c, w in zip(cols, widths)))
    lines.append("-" * (name_w + sum(widths) + 2 * len(widths)))
    for tr in results:
        by_id = {r.check: r for r in tr.results}
        cells = [(_cell(by_id[c.id].grade) if c.id in by_id else "-").ljust(w) for c, w in zip(checks, widths)]
        lines.append(tr.target.name.ljust(name_w) + "  " + "  ".join(cells))
    details = _details(results)
    if details:
        lines += ["", "Details (non-PASS):"] + [f"  {d}" for d in details]
    summary = {g: sum(r.grade == g for tr in results for r in tr.results) for g in ("PASS", WARN, FAIL, "SKIP", ERROR)}
    lines += ["", "Summary: " + ", ".join(f"{g}={n}" for g, n in summary.items() if n)]
    lines.append("Columns: " + ", ".join(f"{c.short}={c.id}" for c in checks))
    return "\n".join(lines)


def render_markdown(results: list[TargetResult], checks: list[CheckSpec]) -> str:
    lines = [f"> {BANNER}", ""] if _is_mock(results) else []
    lines.append("| target | " + " | ".join(c.id for c in checks) + " |")
    lines.append("|---|" + "---|" * len(checks))
    for tr in results:
        by_id = {r.check: r for r in tr.results}
        lines.append(f"| {tr.target.name} | " + " | ".join(_cell(by_id[c.id].grade) if c.id in by_id else "-" for c in checks) + " |")
    details = _details(results)
    if details:
        lines += ["", "### Details (non-PASS)", ""] + [f"- {d}" for d in details]
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


def render(results: list[TargetResult], checks: list[CheckSpec], fmt: str) -> str:
    if fmt == "md":
        return render_markdown(results, checks)
    if fmt == "json":
        return render_json(results)
    return render_text(results, checks)
