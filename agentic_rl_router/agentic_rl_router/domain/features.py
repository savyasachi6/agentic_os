"""
Context feature engineering for the contextual bandit.

Pure domain logic using regex — no FastAPI, no DB, no config.
"""

from __future__ import annotations

import re
from typing import List

import numpy as np

from agentic_rl_router.domain.models import LinguisticFeatures


# ---------------------------------------------------------------------------
# Compiled regex patterns for the 17-feature extractor
# ---------------------------------------------------------------------------

_WH_WORDS = re.compile(
    r"^(who|what|where|when|why|which|how|whom|whose)\b", re.IGNORECASE
)
_QUESTION_MARK = re.compile(r"\?\s*$")
_SUBORDINATION = re.compile(
    r"\b(because|although|though|since|unless|whereas|while|if|when|after|before|until|once|so that)\b",
    re.IGNORECASE,
)
_MULTI_SENTENCE = re.compile(r"[.!?]\s+[A-Z]")
_ENUMERATION = re.compile(
    r"(?:\b\d+[.)]\s)|(?:(?:,\s*\w+){2,}\s*(?:,?\s*(?:and|or)\s))", re.IGNORECASE
)
_NEGATION = re.compile(
    r"\b(not|no|never|neither|nor|n't|don't|doesn't|didn't|won't|wouldn't|can't|cannot|shouldn't|isn't|aren't|wasn't|weren't)\b",
    re.IGNORECASE,
)
_DOMAIN_VOCAB = re.compile(
    r"\b(algorithm|schema|embedding|vector|tensor|gradient|latency|throughput|"
    r"kubernetes|microservice|inference|pipeline|tokenizer|transformer|"
    r"pgvector|postgres|sql|api|llm|rag|gpu|cpu|rrf|cte|hnsw|ann|normalization|"
    r"backpropagation|convolution|hyperparameter|fine-tun|retrieval|indexing)\b",
    re.IGNORECASE,
)
_NAMED_ENTITY = re.compile(r"\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)+\b")
_NUMERIC = re.compile(r"\b\d[\d,.]*\b|(?:\b\d{4}\b)")
_CODE_TOKENS = re.compile(r"`[^`]+`|[a-z]+[A-Z]\w*|\b\w+_\w+\b|(?:def |class |import |from )")
_TEMPORAL = re.compile(
    r"\b(yesterday|today|tomorrow|last\s+(?:week|month|year|day)|"
    r"next\s+(?:week|month|year|day)|in\s+\d{4}|ago|recently|currently|now)\b",
    re.IGNORECASE,
)
_EXPLICIT_CONSTRAINTS = re.compile(
    r"\b(step[- ]by[- ]step|be brief|summarize|in detail|concisely|explain|"
    r"list|enumerate|compare|outline|provide examples)\b",
    re.IGNORECASE,
)
_COMPARISON = re.compile(
    r"\b(compare|comparing|comparison|difference(?:s)? between|differ(?:s)?|vs\.?|versus|"
    r"contrast|pros and cons|advantages|disadvantages)\b",
    re.IGNORECASE,
)
_ANAPHORA = re.compile(
    r"\b(it|they|them|their|this|that|these|those|its|he|she|his|her)\b",
    re.IGNORECASE,
)
_AMBIGUITY = re.compile(
    r"\b(some|maybe|perhaps|kind of|sort of|stuff|things|something|somehow|approximately|roughly)\b",
    re.IGNORECASE,
)
_MULTI_HOP = re.compile(
    r"\b(relate(?:s|d)?\s+to|connection\s+between|how\s+does\s+\w+\s+affect|"
    r"impact(?:s)?\s+on|depends?\s+on|leads?\s+to|results?\s+in|causes?)\b",
    re.IGNORECASE,
)
_HYPOTHETICAL = re.compile(
    r"\b(what if|suppose|imagine|hypothetically|if\s+we|would\s+it|could\s+we|"
    r"assume|in theory|theoretically)\b",
    re.IGNORECASE,
)


def extract_linguistic_features(query: str) -> LinguisticFeatures:
    """Extract 17-dimensional binary linguistic feature vector from raw text."""
    tokens = query.split()
    n_tokens = len(tokens)

    return LinguisticFeatures(
        is_interrogative=bool(_WH_WORDS.search(query) or _QUESTION_MARK.search(query)),
        has_subordination=bool(_SUBORDINATION.search(query)),
        is_multi_sentence=bool(_MULTI_SENTENCE.search(query)),
        is_long_query=n_tokens > 20,
        has_enumeration=bool(_ENUMERATION.search(query)),
        has_negation=bool(_NEGATION.search(query)),
        has_domain_vocabulary=bool(_DOMAIN_VOCAB.search(query)),
        has_named_entities=bool(_NAMED_ENTITY.search(query)),
        has_numeric_content=bool(_NUMERIC.search(query)),
        has_code_tokens=bool(_CODE_TOKENS.search(query)),
        has_temporal_reference=bool(_TEMPORAL.search(query)),
        has_explicit_constraints=bool(_EXPLICIT_CONSTRAINTS.search(query)),
        has_comparison_request=bool(_COMPARISON.search(query)),
        has_anaphora=bool(_ANAPHORA.search(query)),
        has_ambiguity_markers=bool(_AMBIGUITY.search(query)),
        requires_multi_hop=bool(_MULTI_HOP.search(query)),
        has_hypothetical=bool(_HYPOTHETICAL.search(query)),
    )


class ContextFeatureBuilder:
    """Builds a dense numeric context vector for the bandit.

    Layout (1561-d default):
        [0..1535]     query embedding
        [1536..1539]  intent logits
        [1540..1556]  17-d binary linguistic features
        [1557..1560]  session stats
    """

    def __init__(self, embedding_dim: int = 1536) -> None:
        self._embedding_dim = embedding_dim

    def build(
        self,
        *,
        query_text: str,
        query_embedding: List[float],
        intent_logits: List[float] | None = None,
        difficulty_estimate: float = 0.5,
        session_hallucination_rate: float = 0.0,
        previous_depth_hallucinated: bool = False,
        corpus_id: str | None = None,
    ) -> np.ndarray:
        """Build context vector from raw components."""

        # 1. Embedding
        emb = np.array(query_embedding, dtype=np.float64)
        if len(emb) < self._embedding_dim:
            emb = np.pad(emb, (0, self._embedding_dim - len(emb)))
        elif len(emb) > self._embedding_dim:
            emb = emb[: self._embedding_dim]

        # 2. Intent logits
        raw_intents = intent_logits or [0.25, 0.25, 0.25, 0.25]
        intents = np.array(raw_intents[:4], dtype=np.float64)
        if len(intents) < 4:
            intents = np.pad(intents, (0, 4 - len(intents)))

        # 3. Linguistic features
        ling = extract_linguistic_features(query_text)
        ling_vec = np.array(ling.to_vector(), dtype=np.float64)

        # 4. Session stats
        corpus_hash = (
            float(hash(corpus_id) % 1000) / 1000.0 if corpus_id else 0.0
        )
        session_stats = np.array(
            [
                difficulty_estimate,
                session_hallucination_rate,
                float(previous_depth_hallucinated),
                corpus_hash,
            ],
            dtype=np.float64,
        )

        return np.concatenate([emb, intents, ling_vec, session_stats])
