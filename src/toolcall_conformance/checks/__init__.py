"""Check registry and result type."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from ..runner import Context

PASS, WARN, FAIL, SKIP, ERROR = "PASS", "WARN", "FAIL", "SKIP", "ERROR"


@dataclass
class CheckResult:
    check: str
    grade: str
    reason: str = ""
    info: dict[str, Any] = field(default_factory=dict)
    scenarios: list[str] = field(default_factory=list)  # exchanges used as evidence
    sdk_version: str = ""


CheckFn = Callable[["Context"], CheckResult]


@dataclass(frozen=True)
class CheckSpec:
    id: str
    short: str  # column label in terminal tables
    summary: str
    fn: CheckFn


REGISTRY: list[CheckSpec] = []


def register(id: str, short: str, summary: str) -> Callable[[CheckFn], CheckFn]:
    def deco(fn: CheckFn) -> CheckFn:
        REGISTRY.append(CheckSpec(id, short, summary, fn))
        return fn
    return deco


def all_checks() -> list[CheckSpec]:
    # importing registers the checks, in table order
    from . import core, choice, sdk  # noqa: F401
    order = ["nonstream_basic", "content_leak", "args_schema", "stream_assembly", "stream_terminator",
             "sdk_stream_compat", "tool_choice_none", "tool_choice_required", "tool_choice_named",
             "parallel_calls", "roundtrip"]
    return sorted(REGISTRY, key=lambda c: order.index(c.id))
