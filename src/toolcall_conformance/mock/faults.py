"""Deviation modes: each flag changes the wire format of an otherwise valid answer."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Fault:
    name: str
    description: str
    source: str  # where this deviation was observed
    drop_index: bool = False  # streaming tool_calls[] without ``index``
    leak_content: bool = False  # tool call text placed in ``content``, finish_reason stop
    empty_stop: bool = False  # empty content and finish_reason stop
    whole_args: bool = False  # whole tool call in one streamed chunk
    ignore_tool_choice: bool = False  # tool_choice is silently ignored
    bad_json: bool = False  # truncated arguments JSON
    no_done: bool = False  # stream ends without ``data: [DONE]``
    reasoning: bool = False  # ``reasoning`` thinking-token field in deltas/messages
    extra_index: bool = False  # non-stream tool_calls carry an extra ``index`` field


_FAULTS = [
    Fault("good", "No deviation; arguments are split into several fragments.", "OpenAI function calling guide"),
    Fault("no_index", "Streamed tool_calls[] entries have no `index`.", "Gemini OpenAI-compat forum report", drop_index=True),
    Fault("content_leak", "<tool_call>{...}</tool_call> text in content, finish_reason stop.",
          "llama-cpp-python #1784, LM Studio docs", leak_content=True),
    Fault("empty_stop", "Empty content and finish_reason stop.", "silent-failure reports", empty_stop=True),
    Fault("whole_args", "Whole tool call in one streamed chunk.", "Ollama probe, 2026-11-10", whole_args=True),
    Fault("tool_choice_ignored", "tool_choice is ignored.", "Ollama docs, probe", ignore_tool_choice=True),
    Fault("bad_json_args", "Arguments JSON is truncated.", "community reports", bad_json=True),
    Fault("no_done", "Stream ends without `data: [DONE]`.", "SSE terminator in the spec", no_done=True),
    Fault("ollama_like", "whole_args + tool_choice_ignored + reasoning field + extra index.",
          "Ollama 0.40.15 + qwen3:4b probe, 2026-11-10",
          whole_args=True, ignore_tool_choice=True, reasoning=True, extra_index=True),
]

MODES: dict[str, Fault] = {f.name: f for f in _FAULTS}
