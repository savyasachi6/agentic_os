# ADR-001: Upskill Directory Format as the Canonical Skill Representation

## Status

Accepted

## Context

We needed a standard format for encoding agent skills — structured reasoning instructions that get injected into the LLM context at runtime. Options considered:

1. **Upskill format** (`SKILL.md` + `plugin.json` + optional `scripts/`, `references/`) — plain-text, Git-friendly, widely used in HuggingFace's skill ecosystem.
2. **YAML/JSON config files** — structured but less readable for reasoning-heavy instructions.
3. **Database-only** — store skills entirely in PostgreSQL.

## Decision

We adopted the **Upskill directory format** because:

- **Human-readable**: `SKILL.md` is just Markdown — easy to author, review, and version in Git.
- **CoT/ReAct native**: The Markdown structure naturally encodes step-by-step reasoning scaffolds that small models follow without fine-tuning.
- **Ecosystem alignment**: Compatible with HuggingFace Smolagents and the `upskill` CLI for generation and evaluation.
- **Filesystem + DB hybrid**: Skills live on disk (authoritative source of truth) and are indexed into pgvector (for retrieval). This gives us both human-editable files and machine-searchable embeddings.

## Consequences

- Skills must be re-indexed (`SkillIndexer.index_all()`) after any filesystem edit to sync changes to the database.
- The `plugin.json` schema must be kept minimal and stable — breaking changes affect the entire discovery pipeline.
- Token budget constraint: `SKILL.md` should stay under ~700 tokens to avoid dominating small model context windows.
