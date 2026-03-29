-- RL Router: Database Schema for Contextual Bandit Retrieval
-- ========================================================

-- Model weights for bandit persistence (LinUCB)
CREATE TABLE IF NOT EXISTS bandit_weights (
    model_name VARCHAR(255) PRIMARY KEY,
    weights_bin BYTEA NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Episodes: Outcomes of retrieval tasks
CREATE TABLE IF NOT EXISTS retrieval_episodes (
    id VARCHAR(50) PRIMARY KEY,
    query_hash TEXT,
    query_type TEXT,
    depth_used INTEGER,
    speculative_used BOOLEAN,
    latency_ms INTEGER,
    success BOOLEAN,
    hallucination_flag BOOLEAN DEFAULT FALSE,
    hallucination_score DOUBLE PRECISION,
    auditor_score DOUBLE PRECISION,
    faithfulness_score DOUBLE PRECISION,
    coverage_score DOUBLE PRECISION,
    cost_tokens INTEGER,
    reward_scalar DOUBLE PRECISION,
    reward_vector JSONB,
    arm_index INTEGER,
    final_utility_score DOUBLE PRECISION,
    reliable_pass_flag BOOLEAN DEFAULT FALSE,
    context_vector DOUBLE PRECISION[],
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Speculative metrics: Draft/Clustering performance
CREATE TABLE IF NOT EXISTS speculative_metrics (
    id VARCHAR(50) PRIMARY KEY,
    query_hash TEXT,
    n_clusters INTEGER,
    n_drafts INTEGER,
    draft_disagreement DOUBLE PRECISION,
    verifier_confidence DOUBLE PRECISION,
    depth INTEGER,
    latency_ms INTEGER,
    cache_hit BOOLEAN,
    escalation_action TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Tool executions linked to retrieval episodes
CREATE TABLE IF NOT EXISTS agent_tool_executions (
    id VARCHAR(50) PRIMARY KEY,
    episode_id VARCHAR(50) REFERENCES retrieval_episodes(id) ON DELETE CASCADE,
    tool_name TEXT,
    cost_tokens INTEGER,
    execution_latency_ms INTEGER,
    hallucination_type TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indices for performance
CREATE INDEX IF NOT EXISTS idx_retrieval_episodes_query_hash ON retrieval_episodes(query_hash);
CREATE INDEX IF NOT EXISTS idx_retrieval_episodes_created_at ON retrieval_episodes(created_at);
CREATE INDEX IF NOT EXISTS idx_tool_executions_episode_id ON agent_tool_executions(episode_id);
