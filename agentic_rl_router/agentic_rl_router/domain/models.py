"""
Domain models for the RL Router.

These are pure data types used by the bandit, reward, and refinement
domain logic.  They have NO dependency on FastAPI, psycopg2, or any
infrastructure concern.
"""

from __future__ import annotations

from enum import IntEnum, StrEnum
from typing import List

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Action space: 4 depths × 2 speculative toggles = 8 arms
# ---------------------------------------------------------------------------

class RetrievalAction(IntEnum):
    """Discrete routing arms for the contextual bandit."""

    DEPTH_0_SPEC_OFF = 0  # Collapsed tree, no speculative drafting
    DEPTH_0_SPEC_ON = 1   # Collapsed tree, speculative drafting enabled
    DEPTH_1_SPEC_OFF = 2  # Standard RAG, no speculative
    DEPTH_1_SPEC_ON = 3   # Standard RAG, speculative
    DEPTH_2_SPEC_OFF = 4  # Multi-hop GraphRAG, no speculative
    DEPTH_2_SPEC_ON = 5   # Multi-hop GraphRAG, speculative
    DEPTH_3_SPEC_OFF = 6  # Full fractal tree, no speculative
    DEPTH_3_SPEC_ON = 7   # Full fractal tree, speculative

    @property
    def depth(self) -> int:
        return self.value // 2

    @property
    def speculative(self) -> bool:
        return bool(self.value % 2)

    @classmethod
    def from_components(cls, depth: int, speculative: bool) -> "RetrievalAction":
        return cls(depth * 2 + int(speculative))


# ---------------------------------------------------------------------------
# Reward
# ---------------------------------------------------------------------------

class RewardVector(BaseModel):
    """Multi-objective reward decomposition."""

    quality: float = Field(description="r1: answer quality score (0-1)")
    hallucination_penalty: float = Field(description="r2: -λ_H * clamped hallucination score")
    latency_cost: float = Field(description="r3: -λ_L * log(1 + L / L0)")
    overthinking_penalty: float = Field(description="r4: -γ * max(0, depth_used - min_sufficient)")
    scalar: float = Field(description="Scalarised utility after non-linear aggregation")


# ---------------------------------------------------------------------------
# RelyToolBench hallucination taxonomy
# ---------------------------------------------------------------------------

class HallucinationCategory(StrEnum):
    """Differentiated hallucination types from RelyToolBench.

    Each category carries a different penalty in the utility function:
    - none:    No hallucination detected
    - format:  Recoverable via retry (e.g. wrong arg type)
    - timing:  Wasted API call / unnecessary tool use
    - type:    Irrelevant tool chosen entirely
    - content: Fatal — fabricated data or parameters
    """

    NONE = "none"
    FORMAT = "format"
    TIMING = "timing"
    TYPE = "type"
    CONTENT = "content"


class ToolCallLog(BaseModel):
    """Telemetry for a single tool invocation within an episode."""

    tool_name: str = Field(description="Name of the tool or function called")
    cost_tokens: int = Field(default=0, ge=0, description="Tokens consumed by this call")
    execution_latency_ms: float = Field(default=0.0, ge=0.0)
    hallucination_type: HallucinationCategory = Field(
        default=HallucinationCategory.NONE,
        description="RelyToolBench hallucination classification for this call",
    )


# ---------------------------------------------------------------------------
# Linguistic feature vector (QueryBandits-inspired, 17-d binary)
# ---------------------------------------------------------------------------

class LinguisticFeatures(BaseModel):
    """17-dimensional binary feature vector for query characterisation.

    Inspired by QueryBandits (arXiv 2508.16697) Table 1.
    """

    # Syntax / Structure (6)
    is_interrogative: bool = Field(default=False, description="Starts with WH-word or ends with '?'")
    has_subordination: bool = Field(default=False, description="Contains subordinate clauses")
    is_multi_sentence: bool = Field(default=False, description="More than one sentence")
    is_long_query: bool = Field(default=False, description=">20 whitespace-delimited tokens")
    has_enumeration: bool = Field(default=False, description="Enumerations or 3+ conjuncts")
    has_negation: bool = Field(default=False, description="Negation words present")

    # Semantics / Domain (5)
    has_domain_vocabulary: bool = Field(default=False, description="Domain-specific or technical terms")
    has_named_entities: bool = Field(default=False, description="Proper nouns / capitalised phrases")
    has_numeric_content: bool = Field(default=False, description="Numbers, dates, quantities")
    has_code_tokens: bool = Field(default=False, description="Backticks, camelCase, code-like syntax")
    has_temporal_reference: bool = Field(default=False, description="Time expressions")

    # Pragmatics / Intent (4)
    has_explicit_constraints: bool = Field(default=False, description="Instruction markers")
    has_comparison_request: bool = Field(default=False, description="compare, difference between, vs …")
    has_anaphora: bool = Field(default=False, description="Unresolved references (it, they …)")
    has_ambiguity_markers: bool = Field(default=False, description="Vague qualifiers")

    # Meta / Complexity (2)
    requires_multi_hop: bool = Field(default=False, description="Conjunctive or relational phrasing")
    has_hypothetical: bool = Field(default=False, description="what if, suppose, conditional markers")

    def to_vector(self) -> list[int]:
        """Return ordered binary vector for bandit context concatenation."""
        return [
            int(self.is_interrogative),
            int(self.has_subordination),
            int(self.is_multi_sentence),
            int(self.is_long_query),
            int(self.has_enumeration),
            int(self.has_negation),
            int(self.has_domain_vocabulary),
            int(self.has_named_entities),
            int(self.has_numeric_content),
            int(self.has_code_tokens),
            int(self.has_temporal_reference),
            int(self.has_explicit_constraints),
            int(self.has_comparison_request),
            int(self.has_anaphora),
            int(self.has_ambiguity_markers),
            int(self.requires_multi_hop),
            int(self.has_hypothetical),
        ]


# ---------------------------------------------------------------------------
# Refinement actions (π₂)
# ---------------------------------------------------------------------------

class RefineAction(IntEnum):
    """Discrete π₂ actions."""

    ACCEPT = 0
    ESCALATE_DEPTH = 1
    ABORT = 2
