# LLM Lab Architecture

The `llm-lab` provides a controlled environment for testing and optimizing agent reasoning.

## Core Components

- **Evaluator**: Benchmarks different models (via `llm_router`) against standardized reasoning traces (`chains`).
- **Skill Optimizer**: Uses the `skills/upskill` integration to propose edits to `SKILL.md` payloads based on failed task attempts.
- **Analytics Engine**: Aggregates metrics from the `memory.thoughts` table to analyze token density, cost, and "reasoning lift".

## Testing Workflow

1. **Scenario Definition**: A user defines a goal and expected outcome.
2. **Reasoning Trace**: The agent executes the goal across multiple attempts using different models.
3. **Synthesis**: The `llm-lab` generates a "lift report" showing which model/prompt combination had the highest success rate.
