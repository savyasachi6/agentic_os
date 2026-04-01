# LLM & Skills

## Inference Orchestration

The LLM is the "engine" of the appliance. Agentic OS treats it as a stateless resource mediated by the `LLMRouter`.

### Local Inference Backends

- **Ollama**: The default provider for desktop environments.
- **vLLM / vLLM-Router**: Optimized for server environments with high concurrency.

### Micro-Batching

To solve the "one-query-at-a-kind" bottleneck of local GPUs, the router groups independent agent requests into micro-batches, increasing system throughput by up to 5x.

### ReAct Reasoning Loop

Specialist workers (e.g., RAG, Code) operate using a strict **ReAct** (Reasoning + Acting) loop. Every turn must follow this format:

```text
Thought: <internal reasoning about the next step>
Action: <tool_name>(<arguments>)
```

The loop continues until the agent produces the final required action:
`Action: respond_direct(message=""" <final answer> """)`

### Valid Tool Actions
The following core actions are available to the RAG specialist:
- `hybrid_search(query: str)`: Unified search across MSR layers.
- `web_search(query: str)`: Real-time search via DuckDuckGo/Playwright.
- `web_fetch(url: str)`: Full-page content extraction.
- `respond_direct(message: str)`: Final answer delivery to the user.

### Dynamic Context & Injections
- **Skill Retrieval**: Relevant skill fragments are injected based on query intent.
- **Runtime Injections**: The token `{{TODAY}}` is automatically replaced with the current ISO date in the system prompt at runtime to ensure temporal awareness.

> Last updated: arc_change branch

---
See `core/docs/components/llm_router.md` for internal routing logic.
