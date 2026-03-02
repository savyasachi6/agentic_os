# LLM Lab

A sandbox for experimenting with prompt engineering, few-shot examples, and local LLM evaluation.

## Purpose

The `llm-lab` is a developer-focused application layer. It allows users to benchmark different local models (Ollama, vLLM) against specific agent tasks, optimize `SKILL.md` payloads, and test reasoning chains in a repeatable environment.

## Key Features

- **Prompt Benchmarking**: Compare outputs from multiple models for the same prompt side-by-side.
- **Skill Optimizer**: Automated testing of instruction fragments to find the most "reliable" reasoning path.
- **Token Usage Analysis**: Detailed reports on inference cost and latency per agent session.
- **Chain of Thought Visualization**: Replays agent reasoning steps with explicit probability scores for key decisions.

## Usage

```bash
python main.py --project llm-lab --ui
```
