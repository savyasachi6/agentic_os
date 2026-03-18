# ADR-001: Markdown H2/H3 Chunking with Merge/Split

**Status:** Accepted  
**Date:** 2026-03-01

## Context

SKILL.md files need to be split into chunks for embedding. Options:

- Fixed-size character/token windows (naive)
- Semantic splitting by Markdown structure (H2/H3)
- LLM-based splitting

## Decision

Split on H2/H3 headers with merge-small and split-large heuristics.

## Rationale

- **Preserves semantic boundaries**: each chunk corresponds to a section (e.g., "Thinking Process", "Examples").
- **Merge-small** prevents fragments that are too short for meaningful embeddings.
- **Split-large** on paragraph boundaries handles very long sections without cutting mid-sentence.
- **500–800 token window** balances retrieval precision with context coverage. Too small = noisy results; too large = wastes context window.

## Consequences

- Skills with unconventional Markdown (no H2/H3) will be treated as a single chunk.
- Token estimation is approximate (~0.75 words/token). Exact tokenization would require model-specific tokenizer.

---

# ADR-002: Composite Re-ranking with eval_lift

**Status:** Accepted  
**Date:** 2026-03-01

## Context

Raw cosine similarity from pgvector doesn't account for skill quality. A high-similarity but low-quality skill could beat a slightly-lower-similarity but battle-tested one.

## Decision

Use composite scoring: `score = max(chunk_score) * log(1 + eval_lift + 1)`. Filter out skills with `eval_lift < 0`.

## Rationale

- `max(chunk_score)` uses the best-matching chunk to represent the skill.
- `log(1 + eval_lift + 1)` provides a gentle multiplicative boost. A skill with `eval_lift=0` gets `log(2) ≈ 0.69`, while `eval_lift=5` gets `log(7) ≈ 1.95`.
- Negative-lift skills are excluded entirely — they've been shown to hurt model performance.
- The log dampens extreme eval_lift values so a very high-lift skill with poor relevance can't dominate.
