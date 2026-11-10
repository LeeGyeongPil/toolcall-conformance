"""Run checks against targets; share requests between checks; append JSONL as we go."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .checks import ERROR, CheckResult, CheckSpec
from .client import Exchange, post_chat
from .scenarios import build_request
from .targets import Target


class Context:
    """Per-target scenario cache: each distinct request is sent at most once."""

    def __init__(self, target: Target, timeout: float) -> None:
        self.target = target
        self.timeout = timeout
        self._cache: dict[str, Exchange] = {}

    def request(self, scenario: str) -> dict[str, Any]:
        return build_request(scenario, self.target.model)

    def get(self, scenario: str) -> Exchange:
        if scenario not in self._cache:
            ex = post_chat(self.target.base_url, self.request(scenario), scenario,
                           api_key=self.target.api_key, extra_headers=self.target.headers, timeout=self.timeout)
            if ex.is_mock:
                self.target.mock = True
            self._cache[scenario] = ex
        return self._cache[scenario]

    def evidence(self, scenarios: list[str]) -> list[dict[str, Any]]:
        out = []
        for name in scenarios:
            ex = self._cache.get(name)
            if ex:
                out.append({"scenario": name, "request": ex.request, "status": ex.status,
                            "response": ex.text if not ex.sse_lines else None,
                            "sse_lines": ex.sse_lines or None, "error": ex.error or None})
        return out


@dataclass
class TargetResult:
    target: Target
    results: list[CheckResult] = field(default_factory=list)


def result_to_record(target: Target, res: CheckResult, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "target": {"name": target.name, "base_url": target.base_url, "model": target.model,
                   "mock": target.mock, "notes": target.notes},
        "check": res.check, "grade": res.grade, "reason": res.reason, "info": res.info,
        "sdk_version": res.sdk_version or None, "evidence": evidence,
    }


def redact(text: str, secrets: list[str]) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return text


def load_done(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    """Previously recorded (target, check) results from a JSONL file (for --resume)."""
    done: dict[tuple[str, str], dict[str, Any]] = {}
    if not path.exists():
        return done
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
            done[(rec["target"]["name"], rec["check"])] = rec
        except (json.JSONDecodeError, KeyError, TypeError):
            continue  # a half-written last line from an interrupted run
    return done


def run_targets(
    targets: list[Target],
    checks: list[CheckSpec],
    *,
    timeout: float = 180.0,
    out_path: Path | None = None,
    resume: bool = False,
    progress: Callable[[str], None] | None = None,
) -> list[TargetResult]:
    """Run ``checks`` on every target. ``ConnectError`` propagates to the caller."""
    done = load_done(out_path) if (resume and out_path) else {}
    secrets = [t.api_key or "" for t in targets]
    sink = None
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        sink = out_path.open("a" if resume else "w", encoding="utf-8")
    results: list[TargetResult] = []
    try:
        for target in targets:
            ctx = Context(target, timeout)
            tr = TargetResult(target)
            for spec in checks:
                prior = done.get((target.name, spec.id))
                if prior:  # already recorded: skip without sending a request
                    tr.results.append(CheckResult(spec.id, prior["grade"], prior["reason"], prior.get("info") or {},
                                                  sdk_version=prior.get("sdk_version") or ""))
                    target.mock = target.mock or bool(prior["target"].get("mock"))
                    continue
                if progress:
                    progress(f"{target.name}: {spec.id}")
                try:
                    res = spec.fn(ctx)
                except (KeyboardInterrupt, SystemExit):
                    raise
                except Exception as err:  # noqa: BLE001
                    from .client import ConnectError
                    if isinstance(err, ConnectError):
                        raise
                    res = CheckResult(spec.id, ERROR, f"{type(err).__name__}: {err}"[:300])
                ev = ctx.evidence(res.scenarios)
                res.scenarios = res.scenarios or []
                tr.results.append(res)
                if sink:
                    line = json.dumps(result_to_record(target, res, ev), ensure_ascii=False)
                    sink.write(redact(line, secrets) + "\n")
                    sink.flush()  # an interrupted run keeps what finished
            results.append(tr)
    finally:
        if sink:
            sink.close()
    return results
