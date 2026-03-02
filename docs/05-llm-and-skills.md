# LLM & Skills

## Inference Orchestration

The LLM is the "engine" of the appliance. Agentic OS treats it as a stateless resource mediated by the `LLMRouter`.

### Local Inference Backends

- **Ollama**: The default provider for desktop environments.
- **vLLM / vLLM-Router**: Optimized for server environments with high concurrency.

### Micro-Batching

To solve the "one-query-at-a-kind" bottleneck of local GPUs, the router groups independent agent requests into micro-batches, increasing system throughput by up to 5x.

## The Skills Engine

Located in `agentos_skills/`, this system provides the "High-Level Intelligence" beyond core reasoning.

### Reasoning Recipes (`SKILL.md`)

Skills are not just function definitions. They are structured Markdown files containing:

- **System Instructions**: Specific constraints for a domain.
- **Examples**: Few-shot prompts to guide the LLM.
- **Tool Mapping**: Which tools are most effective for this skill.

### Dynamic Context Injection

Instead of a single massive system prompt, the agent *retrieves* the relevant skills for the current turn.

1. **Introspection**: Agent analyzes the query.
2. **Lookup**: Skills engine returns the `k` most relevant skill fragments.
3. **Synthesis**: `agentos_core` assembles the final prompt for the LLM.

---
See `agentos_core/docs/components/llm_router.md` for internal routing logic.
