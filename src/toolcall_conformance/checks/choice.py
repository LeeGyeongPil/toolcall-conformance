"""tool_choice and parallel tool call checks."""

from __future__ import annotations

from . import FAIL, PASS, WARN, CheckResult, register
from .common import message_of, reject_problem


def _calls(ex) -> list[dict] | None:
    got = message_of(ex)
    return None if got is None else (got[0].get("tool_calls") or [])


def _rejected(res: CheckResult, ex) -> CheckResult | None:
    """HTTP 4xx means the server refuses the option: explicit, so WARN rather than FAIL."""
    if 400 <= ex.status < 500:
        res.grade, res.reason = WARN, f"server rejected the option (HTTP {ex.status}): {ex.text.strip()[:120]}"
        return res
    if reject_problem(res, ex):
        return res
    if _calls(ex) is None:
        res.reason = "response has no choices[0].message"
        return res
    return None


@register("tool_choice_none", "none", 'tool_choice "none" suppresses tool calls even when the prompt invites one')
def tool_choice_none(ctx) -> CheckResult:
    ex = ctx.get("choice_none")
    res = CheckResult("tool_choice_none", FAIL, scenarios=["choice_none"])
    if early := _rejected(res, ex):
        return early
    if _calls(ex):
        res.reason = "tool_choice 'none' was ignored: the server still returned tool_calls"
    else:
        res.grade = PASS
    return res


@register("tool_choice_required", "req", 'tool_choice "required" forces a call when the prompt needs no tool')
def tool_choice_required(ctx) -> CheckResult:
    ex = ctx.get("choice_required")
    res = CheckResult("tool_choice_required", FAIL, scenarios=["choice_required"])
    if early := _rejected(res, ex):
        return early
    if not _calls(ex):
        res.reason = "tool_choice 'required' was ignored: no tool_calls for a prompt that needs none"
    else:
        res.grade = PASS
    return res


@register("tool_choice_named", "named", "tool_choice naming a function forces that function")
def tool_choice_named(ctx) -> CheckResult:
    ex = ctx.get("choice_named")
    res = CheckResult("tool_choice_named", FAIL, scenarios=["choice_named"])
    if early := _rejected(res, ex):
        return early
    names = [(c.get("function") or {}).get("name") for c in _calls(ex) or []]
    if not names:
        res.reason = "named tool_choice was ignored: no tool_calls"
    elif set(names) != {"get_time"}:
        res.reason = f"asked for get_time but got {names}"
    else:
        res.grade = PASS
    return res


@register("parallel_calls", "para", "Two independent requests produce two tool_calls in one turn (WARN if only one)")
def parallel_calls(ctx) -> CheckResult:
    ex = ctx.get("parallel")
    res = CheckResult("parallel_calls", FAIL, scenarios=["parallel"])
    if early := _rejected(res, ex):
        return early
    n = len(_calls(ex) or [])
    res.info = {"tool_calls": n}
    if n >= 2:
        res.grade = PASS
    elif n == 1:
        res.grade, res.reason = WARN, "only one tool call for two independent requests (parallel calls may be unsupported)"
    else:
        res.reason = "no tool_calls"
    return res
