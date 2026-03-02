-- schema.sql
-- Agentic RL Router: Telemetry & Metrics Schema

CREATE TYPE hallucination_category AS ENUM ('none', 'type', 'timing', 'format', 'content');

CREATE TABLE IF NOT EXISTS retrieval_episodes (
    id                    VARCHAR(64) PRIMARY KEY,
    query_hash            TEXT NOT NULL,
    query_type            TEXT,
    depth_used            INT,
    speculative_used      BOOLEAN DEFAULT FALSE,
    latency_ms            INT,
    success               BOOLEAN,
    hallucination_flag    BOOLEAN DEFAULT FALSE,
    hallucination_score   FLOAT DEFAULT 0.0,
    auditor_score         FLOAT,
    faithfulness_score    FLOAT,
    coverage_score        FLOAT,
    cost_tokens           INT,
    reward_scalar         FLOAT,
    reward_vector         JSONB,           -- DEPRECATED: {quality, hallucination, latency, overthinking}
    final_utility_score   FLOAT,
    reliable_pass_flag    BOOLEAN DEFAULT FALSE,
    arm_index             INT,
    created_at            TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agent_tool_executions (
    id                    VARCHAR(64) PRIMARY KEY,
    episode_id            VARCHAR(64) REFERENCES retrieval_episodes(id) ON DELETE CASCADE,
    tool_name             VARCHAR(128) NOT NULL,
    cost_tokens           INTEGER DEFAULT 0,
    execution_latency_ms  FLOAT,
    hallucination_type    hallucination_category DEFAULT 'none',
    created_at            TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS speculative_metrics (
    id                    VARCHAR(64) PRIMARY KEY,
    query_hash            TEXT NOT NULL,
    n_clusters            INT,
    n_drafts              INT,
    draft_disagreement    FLOAT,          -- entropy over draft answers
    verifier_confidence   FLOAT,
    depth                 INT,
    latency_ms            INT,
    cache_hit             BOOLEAN,
    escalation_action     TEXT,           -- accept / escalate / abort
    created_at            TIMESTAMPTZ DEFAULT NOW()
);
