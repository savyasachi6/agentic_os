# LLM & Skills

## Inference Orchestration

The LLM is the reasoning engine of Agentic OS. All LLM calls from any agent pass through the **`LLMRouter`** (`agent_core/llm/router.py`), which abstracts backend selection and provides micro-batching.

### LLM Backends (`agent_core/llm/backends/`)

| Backend | Class | When Used |
|---|---|---|
| `OllamaBackend` | `ollama_api.py` | Default for local desktop environments |
| `LlamaCPPBackend` | `llama_native.py` | Native llama.cpp server (set `ROUTER_BACKEND=llama-cpp`) |
| `OpenAIBackend` | `openai_api.py` | OpenAI-compatible APIs incl. OpenRouter (set `ROUTER_BACKEND=openai`) |

The primary backend is selected from the `ROUTER_BACKEND` env var. **Fallback**: if the primary is a cloud backend and receives a fatal error (HTTP 401/429), the router automatically fails over to a local **Ollama fallback** with a 5-minute cloud cooldown.

### Model Tiers (`agent_core/llm/models.py`)

| Tier | Purpose | Config Key |
|---|---|---|
| `NANO` | Fast lightweight calls (query rewriting, small lookups) | `OLLAMA_MODEL_NANO` |
| `FAST` | Intermediate quality (session compaction summaries) | `OLLAMA_MODEL_FAST` |
| `FULL` | Primary reasoning (all specialist ReAct loops) | `OLLAMA_MODEL_FULL` |

If `OPENROUTER_API_KEY` is set and the configured `FULL` model looks like a local model (contains `:` or `ollama`), the router automatically overrides it to `deepseek/deepseek-r1:free`.

### Micro-Batching

The `LLMRouter` uses a **priority-sorted async queue** with configurable `ROUTER_BATCH_SIZE`. Requests from multiple concurrent specialists are grouped by `(model, max_tokens, temperature, stop_sequences)` and dispatched as a single batch to the backend. Results are demultiplexed back to individual agent `asyncio.Future` objects.

`NANO` tier requests are automatically elevated to `OBSERVER` priority (highest) to ensure query rewriting never blocks behind heavy reasoning tasks.

---

## ReAct Reasoning Loop

All specialist workers implement a strict **ReAct** (Reasoning + Acting) loop. Every LLM turn must produce:

```text
Thought: <internal reasoning about the next step>
Action: <tool_name>(<arguments>)
```

The loop continues until the agent calls the terminal action:

```text
Action: respond_direct(message="""<final answer>""")
```

### Loop Hardening (Current Implementation)

- **Max Turns**: Configurable per task via `max_turns` in the node payload (default: 4).
- **Last-Turn Nudge**: When `i == max_turns - 2`, a user message is injected: *"You have ONE turn remaining. After the next Observation, call `respond_direct(...)` with your complete answer."*
- **Empty Response Guard**: If the LLM returns an empty string, the turn is skipped (not appended to history) to avoid poisoning the message context.
- **No-Action Nudge**: If no `Action:` line is parsed, a `Observation: I didn't see an 'Action:' line...` message is injected to recover formatting compliance.
- **Abandonment Check**: Each turn verifies the node is still `PENDING` or `RUNNING` before proceeding — aborts if the coordinator has already cancelled the task.
- **Native Thinking Tokens**: The parser strips `<|thinking|>...<|/thinking|>` model-native thinking blocks from response text before action parsing.

### Valid Tool Actions (RAG Specialist)

| Action | Signature | Description |
|---|---|---|
| `hybrid_search` | `hybrid_search(query="...")` | Invokes `CognitiveRetriever.retrieve_context()`. Returns MSR-fused context block. |
| `web_search` | `web_search(query="...")` | DuckDuckGo search via `agent_core/tools/tools.py:WebSearchAction`. |
| `web_fetch` | `web_fetch(url="...")` | HTTP GET + BeautifulSoup text extraction (httpx, 30s timeout, truncated at 10k chars). |
| `respond_direct` | `respond_direct(message="""...""")` | Final answer delivery — terminates the loop and marks the node `DONE`. |

### Dynamic Context Injections

- **Date Injection**: `{{TODAY}}` and `{current_date}` tokens in system prompts are replaced with the current ISO date at task start. If no `Today is` line is present, the date is prepended.
- **Thought Publishing**: Parsed thought text is normalized (via `agent_core/utils/thought_utils.py`) and published to the A2A Bus as a `thought` event so the UI reasoning accordion stays live.

---

## System Prompts (`prompts/`)

System prompts are stored as Markdown files in `prompts/` and loaded at worker startup via `agent_core/prompts.py:load_prompt(group, name)`. If loading fails, workers fall back to an inline default.

| Agent | Prompt Key |
|---|---|
| Coordinator | `load_prompt("core", "coordinator")` |
| RAG Worker | `load_prompt("agents", "rag")` |

> Last updated: arc_change branch — verified against source

