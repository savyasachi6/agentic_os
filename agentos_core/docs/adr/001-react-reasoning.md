# ADR-001: ReAct Reasoning Framework

**Status:** Accepted  
**Date:** 2026-03-01

## Context

We need a reasoning framework for smaller local models (e.g., Llama 3.2 7B). Options:

- **ReAct** (Thought/Action/Observation in plain text)
- **Function calling** (structured JSON tool calls, requires model support)
- **Plan-and-Execute** (separate planning + execution phases)

## Decision

Use **ReAct** with text-based parsing.

## Rationale

- **Model compatibility**: 7B models have varying function-calling support. Text-based ReAct works with any chat model.
- **Transparency**: Thought steps are visible and storable — we log every `Thought:` to pgvector for CoT continuity.
- **Skill integration**: SKILL.md files already use ReAct-style scaffolding.
- **LPX readiness**: Switching to structured function calling later is a straightforward parser change.

## Consequences

- Parsing is regex-based and can be fragile.
- Iteration caps are required to prevent infinite loops.
