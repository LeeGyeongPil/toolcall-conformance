# Checks

Every check sends fixed tools (`get_weather(city)`, `get_time(timezone)`) at temperature 0 and judges the
**wire format**, not the model's accuracy. Requests are shared between checks, so a full run needs about
8 requests. Grades: `PASS`, `WARN` (legal but worth knowing), `FAIL`, `SKIP` (nothing to judge), `ERROR` (check crashed or timed out).
One run is a clue, not a verdict: models are not fully deterministic even at temperature 0.

| Check | What it looks at | FAIL when | Usual causes |
|---|---|---|---|
| `nonstream_basic` | `message.tool_calls[]` with `id`, `type: "function"`, `function.name`, `function.arguments` (a JSON *string*), `finish_reason: "tool_calls"` | no tool calls, empty content with `stop`, wrong `finish_reason` | server has no tool parser for the model |
| `content_leak` | tool call text in `content` (`<tool_call>`, `[TOOL_CALLS]`, `<\|python_tag\|>`, `{"name": "get_weather"...}`); `reasoning` / `reasoning_content` are ignored | pattern found | vLLM without `--enable-auto-tool-choice` and a matching `--tool-call-parser`; llama-server without `--jinja`; parser failed |
| `args_schema` | `arguments` parse as JSON and satisfy `required` and basic types | invalid JSON / missing field | truncated generation, template mismatch |
| `stream_assembly` | `delta.tool_calls[]` merged by `index`; `id`/`name` present; final `finish_reason` | no `index`, no calls, wrong finish | proxies or compat layers that drop `index` |
| `stream_terminator` | stream ends with `data: [DONE]` | missing | proxy truncation |
| `sdk_stream_compat` | the official `openai` Python SDK stream helper assembles the same request | the SDK raises or finds no calls | missing `index` (the SDK merges fragments by it) |
| `tool_choice_none` | prompt invites a call, `tool_choice: "none"` | tool calls returned (ignored) | server does not implement `tool_choice` |
| `tool_choice_required` | prompt needs no tool, `tool_choice: "required"` | no tool calls | same; older vLLM (`required` needs 0.8.3+) |
| `tool_choice_named` | forces `get_time` while the prompt hints `get_weather` | other function | same |
| `parallel_calls` | two independent requests -> two calls | no calls (`WARN` for one call) | model or server default is sequential |
| `roundtrip` | `assistant.tool_calls` + `tool` message with `tool_call_id`, then a final answer with `stop` | HTTP error, another tool call, empty answer | template does not support the `tool` role |

HTTP 4xx on a `tool_choice` or `parallel` request is graded `WARN` ("server rejected the option"): refusing explicitly is honest behavior.

## Sources (checked 2026-11-10)

- OpenAI function calling guide: https://developers.openai.com/api/docs/guides/function-calling
- Ollama OpenAI compatibility: https://docs.ollama.com/api/openai-compatibility
- llama.cpp function calling: https://github.com/ggml-org/llama.cpp/blob/master/docs/function-calling.md
- vLLM tool calling: https://docs.vllm.ai/en/latest/features/tool_calling.html
- LM Studio tool use: https://lmstudio.ai/docs/developer/openai-compat/tools
