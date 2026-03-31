-- ============================================================
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- Tools registry
-- ============================================================
CREATE TABLE IF NOT EXISTS tools (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    risk_level  VARCHAR(16) DEFAULT 'low',
    endpoint    VARCHAR(512),
    docs        TEXT,
    tags        TEXT[],
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- RAG: Skills (Canonical entities)
-- ============================================================
CREATE TABLE IF NOT EXISTS knowledge_skills (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(255) NOT NULL,
    normalized_name VARCHAR(255) NOT NULL UNIQUE, -- lowercase_slug
    skill_type      VARCHAR(64) NOT NULL,         -- framework, concept, tool, language
    description     TEXT,
    aliases         TEXT[],
    metadata_json   JSONB DEFAULT '{}',
    path            TEXT,
    checksum        VARCHAR(64),                  -- SHA-256 for incremental indexing
    eval_lift       FLOAT DEFAULT 0.0,
    deleted_at      TIMESTAMP,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_skills_normalized ON knowledge_skills (normalized_name);
CREATE INDEX IF NOT EXISTS idx_skills_fulltext ON knowledge_skills (normalized_name); -- Fallback if tsvector not ready

-- ============================================================
-- System/agent events
-- ============================================================
CREATE TABLE IF NOT EXISTS events (
    id          SERIAL PRIMARY KEY,
    session_id  VARCHAR(255),
    source      VARCHAR(50) NOT NULL,     -- agent / tool / system
    event_type  VARCHAR(50) NOT NULL,     -- log / process / error / security
    data        JSONB NOT NULL DEFAULT '{}',
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_events_session ON events (session_id);

-- ============================================================
-- Skill chunks: embedded pieces of SKILL.md content
-- ============================================================
CREATE TABLE IF NOT EXISTS skill_chunks (
    id          SERIAL PRIMARY KEY,
    skill_id    INTEGER REFERENCES knowledge_skills(id) ON DELETE CASCADE,
    chunk_type  VARCHAR(50),  -- 'frontmatter', 'instructions', 'examples', 'scripts_ref'
    heading     VARCHAR(512), -- section heading this chunk came from
    content     TEXT NOT NULL,
    embedding   VECTOR(1024),
    token_count INTEGER
);

CREATE INDEX IF NOT EXISTS idx_skill_chunks_hnsw
    ON skill_chunks USING hnsw (embedding vector_cosine_ops);

-- ============================================================
-- Thoughts: per-turn agent reasoning log
-- ============================================================
CREATE TABLE IF NOT EXISTS thoughts (
    id          SERIAL PRIMARY KEY,
    session_id  VARCHAR(255) NOT NULL,
    role        VARCHAR(50) NOT NULL,  -- 'user', 'assistant', 'tool', 'thought'
    content     TEXT NOT NULL,
    embedding   VECTOR(1024),
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_thoughts_session ON thoughts (session_id);
CREATE INDEX IF NOT EXISTS idx_thoughts_hnsw
    ON thoughts USING hnsw (embedding vector_cosine_ops);

-- ============================================================
-- Session summaries: compacted CoT memory
-- ============================================================
CREATE TABLE IF NOT EXISTS session_summaries (
    id          SERIAL PRIMARY KEY,
    session_id  VARCHAR(255) NOT NULL,
    summary     TEXT NOT NULL,
    embedding   VECTOR(1024),
    turn_start  INTEGER,     -- first turn index covered
    turn_end    INTEGER,     -- last turn index covered
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_session_summaries_session ON session_summaries (session_id);
CREATE INDEX IF NOT EXISTS idx_session_summaries_hnsw
    ON session_summaries USING hnsw (embedding vector_cosine_ops);

-- ============================================================
-- Lanes: ordered execution queues per session
-- ============================================================
CREATE TABLE IF NOT EXISTS lanes (
    id          VARCHAR(64) PRIMARY KEY,
    session_id  VARCHAR(255) NOT NULL,
    name        VARCHAR(128) DEFAULT 'default',
    risk_level  VARCHAR(16) DEFAULT 'normal',   -- low / normal / high
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_lanes_session ON lanes (session_id);

-- ============================================================
-- Commands: every agent action, queued in lane order
-- ============================================================
CREATE TABLE IF NOT EXISTS commands (
    id          VARCHAR(64) PRIMARY KEY,
    lane_id     VARCHAR(64) NOT NULL REFERENCES lanes(id) ON DELETE CASCADE,
    seq         INTEGER NOT NULL,                -- execution order within lane
    status      VARCHAR(16) DEFAULT 'pending',   -- pending / running / done / failed / cancelled
    cmd_type    VARCHAR(32) NOT NULL,            -- plan / llm_call / tool_call / human_review
    tool_name   VARCHAR(128),
    payload     JSONB NOT NULL DEFAULT '{}',
    result      JSONB,
    error       TEXT,
    sandbox_id  VARCHAR(128),
    priority    INTEGER DEFAULT 5,               -- higher number = executed first
    depends_on  VARCHAR(64)[],                   -- DAG formulation: list of parent command ids
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at  TIMESTAMP,
    finished_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_commands_lane_status ON commands (lane_id, status, seq);
CREATE INDEX IF NOT EXISTS idx_commands_lane_seq ON commands (lane_id, seq);

-- ============================================================
-- Multi-step workflow chains (Overrides existing chains schema for appliance)
-- ============================================================
DROP TABLE IF EXISTS nodes CASCADE;
DROP TABLE IF EXISTS chains CASCADE;

CREATE TABLE IF NOT EXISTS chains (
    id          SERIAL PRIMARY KEY,
    session_id  VARCHAR(255) NOT NULL,
    description TEXT,
    status      VARCHAR(16) DEFAULT 'active',
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_chains_session ON chains (session_id);

CREATE TABLE IF NOT EXISTS chain_steps (
    id          SERIAL PRIMARY KEY,
    chain_id    INTEGER REFERENCES chains(id) ON DELETE CASCADE,
    seq         INTEGER NOT NULL,
    step_type   VARCHAR(32) NOT NULL,     -- llm / tool / human / skill
    input       JSONB,
    output      JSONB,
    skill_id    INTEGER REFERENCES knowledge_skills(id),
    tool_id     INTEGER REFERENCES tools(id),
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- Nodes: individual execution steps in a tree
-- ============================================================
CREATE TABLE IF NOT EXISTS nodes (
    id SERIAL PRIMARY KEY,
    chain_id INTEGER NOT NULL REFERENCES chains(id) ON DELETE CASCADE,
    parent_id INTEGER REFERENCES nodes(id) ON DELETE SET NULL,
    agent_role VARCHAR(50) NOT NULL,    -- rag, schema, tools, etc.
    type VARCHAR(50) NOT NULL,          -- plan, llm_call, tool_call, result, summary
    status VARCHAR(16) DEFAULT 'pending', -- pending, running, done, failed
    priority INTEGER DEFAULT 5,         -- 1=low, 10=urgent
    planned_order INTEGER DEFAULT 0,    -- execution sequence within siblings
    content TEXT,                       -- raw text or json payload
    payload JSONB DEFAULT '{}',         -- structured input task arguments
    result JSONB,                       -- structured output from the agent
    embedding VECTOR(1024),              -- 1536 to match the rest of the embedding columns
    deadline_at TIMESTAMP,
    fractal_depth INT DEFAULT 0,
    draft_cluster INT,
    is_degraded BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_nodes_chain ON nodes (chain_id);
CREATE INDEX IF NOT EXISTS idx_nodes_parent ON nodes (parent_id);
CREATE INDEX IF NOT EXISTS idx_nodes_fractal ON nodes (fractal_depth, parent_id); -- Optimized for recursive tree visualization
CREATE INDEX IF NOT EXISTS idx_nodes_status_priority ON nodes (chain_id, status, priority DESC, planned_order ASC);
CREATE INDEX IF NOT EXISTS idx_nodes_hnsw ON nodes USING hnsw (embedding vector_cosine_ops);

-- ============================================================
-- RAG: Documents (High-level metadata for sources)
-- ============================================================
CREATE TABLE IF NOT EXISTS documents (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_type   VARCHAR(64) NOT NULL, -- file, web, s3, internal_spec
    source_uri    VARCHAR(1024) NOT NULL UNIQUE,
    title         TEXT,
    language      VARCHAR(16) DEFAULT 'en',
    author        VARCHAR(255),
    checksum      VARCHAR(64),          -- SHA-256 for idempotency
    version       VARCHAR(32) DEFAULT '1.0.0',
    metadata_json JSONB DEFAULT '{}',
    deleted_at    TIMESTAMP,            -- Soft delete support
    ingested_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_documents_source_type ON documents (source_type);
CREATE INDEX IF NOT EXISTS idx_documents_uri ON documents (source_uri);

-- ============================================================
-- RAG: Chunks (Structure-aware segments)
-- ============================================================
CREATE TABLE IF NOT EXISTS chunks (
    id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id    UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index    INTEGER NOT NULL,
    content_hash   CHAR(32),    -- MD5 hash for idempotent ingestion
    raw_text       TEXT NOT NULL,
    clean_text     TEXT,
    token_count    INTEGER,
    section_path   TEXT, -- hierarchy_label e.g. "Chapter 1 > Section 2.1"
    llm_summary    TEXT,
    llm_tags       TEXT[],
    enrichment_json JSONB DEFAULT '{}',
    chunk_metadata JSONB DEFAULT '{}',
    fulltext_weighted TSVECTOR, -- For GIN-based lexical search
    deleted_at     TIMESTAMP,   -- Soft delete support
    parent_chunk_id UUID REFERENCES chunks(id) ON DELETE SET NULL, -- For hierarchy/Dynamic Zooming
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(document_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks (document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_parent ON chunks (parent_chunk_id);
CREATE INDEX IF NOT EXISTS idx_chunks_fulltext ON chunks USING GIN (fulltext_weighted);
CREATE INDEX IF NOT EXISTS idx_chunks_tags ON chunks USING GIN (llm_tags);
CREATE INDEX IF NOT EXISTS idx_chunks_metadata ON chunks USING GIN (chunk_metadata); -- Support rapid metadata filtering

-- ============================================================
-- RAG: Chunk Signatures (Deduplication)
-- ============================================================
CREATE TABLE IF NOT EXISTS chunk_signatures (
    chunk_id UUID PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE,
    simhash  BIGINT NOT NULL, -- lightweight signature for near-duplicate detection
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_chunk_signatures_simhash ON chunk_signatures (simhash);

-- Trigger to maintain fulltext search
CREATE OR REPLACE FUNCTION chunks_tsvector_trigger() RETURNS trigger AS $$
begin
  new.fulltext_weighted :=
    setweight(to_tsvector('english', coalesce(new.raw_text, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(new.llm_summary, '')), 'B');
  return new;
end
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_chunks_tsvector ON chunks;
CREATE TRIGGER trg_chunks_tsvector BEFORE INSERT OR UPDATE
    ON chunks FOR EACH ROW EXECUTE FUNCTION chunks_tsvector_trigger();

-- ============================================================
-- RAG: Chunk Embeddings (pgvector)
-- ============================================================
CREATE TABLE IF NOT EXISTS chunk_embeddings (
    chunk_id   UUID PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE,
    embedding  VECTOR(1024) NOT NULL,
    model_name VARCHAR(128) NOT NULL,
    dimension  INTEGER DEFAULT 1024,
    is_current BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- HNSW Index for fast ANN search (Tuned for 100k+ chunks)
CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_hnsw
    ON chunk_embeddings USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 128);

-- ============================================================
-- RAG: General Entities
-- ============================================================
CREATE TABLE IF NOT EXISTS entities (
    id              SERIAL PRIMARY KEY,
    entity_type     VARCHAR(64) NOT NULL, -- person, project, tool, org
    name            VARCHAR(255) NOT NULL,
    normalized_name VARCHAR(255) NOT NULL UNIQUE,
    description     TEXT,
    metadata_json   JSONB DEFAULT '{}',
    relation_count  INTEGER DEFAULT 0,    -- Cached degree to mitigate "Supernode" bottlenecks
    deleted_at      TIMESTAMP,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- RAG: Decoupled Scoring (Mitigates Write Amplification)
-- ============================================================
CREATE TABLE IF NOT EXISTS chunk_scores (
    chunk_id        UUID PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE,
    performance_score FLOAT4 DEFAULT 0.0, -- Decoupled from heavy vector table
    feedback_count  INTEGER DEFAULT 0,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_chunk_scores_perf ON chunk_scores (performance_score DESC);

-- ============================================================
-- RAG: Knowledge Graph Relations
-- ============================================================
CREATE TABLE IF NOT EXISTS entity_relations (
    id                 SERIAL PRIMARY KEY,
    source_entity_id   INTEGER NOT NULL,
    source_entity_type VARCHAR(64) NOT NULL, -- 'skill' or 'entity'
    target_entity_id   INTEGER NOT NULL,
    target_entity_type VARCHAR(64) NOT NULL, -- 'skill' or 'entity'
    relation_type      VARCHAR(64) NOT NULL, -- REQUIRES, RELATED_TO, PART_OF, USES
    weight             FLOAT DEFAULT 1.0,
    metadata_json      JSONB DEFAULT '{}',
    created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_entity_id, target_entity_id, relation_type)
);

CREATE INDEX IF NOT EXISTS idx_entity_relations_src ON entity_relations (source_entity_id, relation_type);
CREATE INDEX IF NOT EXISTS idx_entity_relations_tgt ON entity_relations (target_entity_id, relation_type);
CREATE INDEX IF NOT EXISTS idx_entity_relations_subject ON entity_relations (source_entity_id, relation_type); -- Support bi-directional traversal
CREATE INDEX IF NOT EXISTS idx_entity_relations_object ON entity_relations (target_entity_id, relation_type);

-- Trigger to maintain relation_count for KG Supernode mitigation
CREATE OR REPLACE FUNCTION update_entity_relation_count() RETURNS trigger AS $$
BEGIN
    IF (TG_OP = 'INSERT') THEN
        UPDATE entities SET relation_count = relation_count + 1 WHERE id = NEW.source_entity_id OR id = NEW.target_entity_id;
    ELSIF (TG_OP = 'DELETE') THEN
        UPDATE entities SET relation_count = relation_count - 1 WHERE id = OLD.source_entity_id OR id = OLD.target_entity_id;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_entity_relations_count ON entity_relations;
CREATE TRIGGER trg_entity_relations_count
AFTER INSERT OR DELETE ON entity_relations
FOR EACH ROW EXECUTE FUNCTION update_entity_relation_count();

-- ============================================================
-- RAG: Chunk-Entity Bridge
-- ============================================================
CREATE TABLE IF NOT EXISTS chunk_entities (
    chunk_id   UUID REFERENCES chunks(id) ON DELETE CASCADE,
    entity_id  INTEGER REFERENCES entities(id) ON DELETE CASCADE,
    confidence FLOAT DEFAULT 1.0,
    source     VARCHAR(64) DEFAULT 'llm_extraction',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (chunk_id, entity_id)
);

CREATE INDEX IF NOT EXISTS idx_chunk_entities_eid ON chunk_entities (entity_id);

-- ============================================================
-- RAG: Usage Audit and Feedback
-- ============================================================
CREATE TABLE IF NOT EXISTS retrieval_events (
    id               UUID DEFAULT uuid_generate_v4(),
    session_id       VARCHAR(255) NOT NULL,
    query_text       TEXT NOT NULL,
    strategy_used    VARCHAR(64), -- vector, hybrid, graph_walk
    top_k            INTEGER,
    retrieved_chunk_ids UUID[],
    latency_ms       INTEGER,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

-- Example partition
CREATE TABLE IF NOT EXISTS retrieval_events_y2026m03 PARTITION OF retrieval_events
    FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');

CREATE INDEX IF NOT EXISTS idx_retrieval_events_session ON retrieval_events (session_id);
CREATE INDEX IF NOT EXISTS idx_retrieval_events_chunks ON retrieval_events USING GIN (retrieved_chunk_ids);

CREATE TABLE IF NOT EXISTS event_chunks (
    id               SERIAL,
    event_id         UUID NOT NULL,
    chunk_id         UUID NOT NULL,
    session_id       VARCHAR(255), -- De-normalized for fast session reconstruction
    retrieval_score  FLOAT,
    reranker_score   FLOAT,        -- Standard observability for 2-stage retrieval
    final_score      FLOAT,        -- Final score after weighting and reranking
    auditor_relevance FLOAT,
    hallucination_flag BOOLEAN DEFAULT FALSE,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (event_id, chunk_id, created_at)
) PARTITION BY RANGE (created_at);

-- Example partition (to be managed by automation or migration)
CREATE TABLE IF NOT EXISTS event_chunks_y2026m03 PARTITION OF event_chunks
    FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');

CREATE INDEX IF NOT EXISTS idx_event_chunks_event_chunk ON event_chunks (chunk_id, event_id);
CREATE INDEX IF NOT EXISTS idx_event_chunks_session ON event_chunks (session_id);

CREATE TABLE IF NOT EXISTS audit_feedback (
    id                SERIAL PRIMARY KEY,
    retrieval_event_id UUID,
    auditor_role      VARCHAR(64) NOT NULL, -- gatekeeper, auditor, strategist
    quality_score     FLOAT,                -- 0.0 to 1.0
    is_negative       BOOLEAN DEFAULT FALSE, -- Strategic flag for RLHF optimization
    hallucination_flag BOOLEAN DEFAULT FALSE,
    missing_context_flag BOOLEAN DEFAULT FALSE,
    comments          TEXT,
    metadata_json     JSONB DEFAULT '{}',
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_audit_feedback_negative ON audit_feedback (retrieval_event_id) WHERE is_negative = true;

-- ============================================================
-- RAG: Semantic Cache
-- ============================================================
CREATE TABLE IF NOT EXISTS semantic_cache (
    id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    query_hash        CHAR(32) NOT NULL UNIQUE,     -- MD5 of normalized query text
    query_vector      VECTOR(1024) NOT NULL,
    response_payload  JSONB NOT NULL,
    strategy_used     VARCHAR(64),
    staleness_version INTEGER DEFAULT 1,
    is_hot            BOOLEAN DEFAULT FALSE,        -- For "Hot Cache" partial indexing
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_accessed_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Partial Index for the "Hot Cache" to ensure performance stability
CREATE INDEX IF NOT EXISTS idx_semantic_cache_hot_hnsw
    ON semantic_cache USING hnsw (query_vector vector_cosine_ops)
    WHERE is_hot = true;

CREATE INDEX IF NOT EXISTS idx_semantic_cache_hnsw 
    ON semantic_cache USING hnsw (query_vector vector_cosine_ops);

-- ============================================================
-- Hybrid Search Stored Procedure
-- ============================================================
CREATE OR REPLACE FUNCTION hybrid_search(
    query_vec VECTOR(1024),
    query_text TEXT,
    match_limit INTEGER DEFAULT 5
)
RETURNS TABLE (
    chunk_id UUID,
    content TEXT,
    source_uri VARCHAR(1024),
    combined_score FLOAT
) AS $$
BEGIN
    RETURN QUERY
    WITH semantic_search AS (
        SELECT 
            c.id, 
            c.document_id, 
            c.raw_text,
            ROW_NUMBER() OVER (ORDER BY ce.embedding <=> query_vec) as rank
        FROM chunks c
        JOIN chunk_embeddings ce ON c.id = ce.chunk_id
        WHERE c.deleted_at IS NULL
        ORDER BY ce.embedding <=> query_vec
        LIMIT match_limit * 2
    ),
    keyword_search AS (
        SELECT 
            c.id, 
            c.document_id, 
            c.raw_text,
            ROW_NUMBER() OVER (ORDER BY ts_rank_cd(c.fulltext_weighted, websearch_to_tsquery('english', query_text)) DESC) as rank
        FROM chunks c
        WHERE c.fulltext_weighted @@ websearch_to_tsquery('english', query_text)
          AND c.deleted_at IS NULL
        LIMIT match_limit * 2
    )
    SELECT 
        COALESCE(s.id, k.id) AS chunk_id,
        COALESCE(s.raw_text, k.raw_text) AS content,
        d.source_uri,
    (
            (COALESCE(1.0 / (60 + s.rank), 0.0) + COALESCE(1.0 / (60 + k.rank), 0.0)) +
            (0.05 * COALESCE(cs.performance_score, 0.0)) -- Adaptive boost (Matthew Effect Mitigated)
        )::FLOAT AS combined_score
    FROM semantic_search s
    FULL OUTER JOIN keyword_search k ON s.id = k.id
    JOIN documents d ON d.id = COALESCE(s.document_id, k.document_id)
    LEFT JOIN chunk_scores cs ON cs.chunk_id = COALESCE(s.id, k.id)
    ORDER BY combined_score DESC
    LIMIT match_limit;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- Speculative Fractal RAG: Draft Storage
-- ============================================================
CREATE TABLE IF NOT EXISTS rag_drafts (
    id              VARCHAR(64) PRIMARY KEY,
    query_hash      TEXT NOT NULL,
    draft_cluster   INT,                      -- k-means cluster index (0,1,2,3)
    draft_content   TEXT NOT NULL,
    confidence      FLOAT DEFAULT 0.0,
    chunk_ids       VARCHAR(64)[],            -- source chunk traceability
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rag_drafts_query ON rag_drafts (query_hash);
CREATE INDEX IF NOT EXISTS idx_rag_drafts_confidence ON rag_drafts (query_hash, confidence DESC);

-- ============================================================
-- Content Dependency Graph (Fractal Cache Staleness)
-- ============================================================
CREATE TABLE IF NOT EXISTS content_deps (
    parent_hash     TEXT NOT NULL,
    child_hash      TEXT NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (parent_hash, child_hash)
);

CREATE INDEX IF NOT EXISTS idx_content_deps_parent ON content_deps (parent_hash, child_hash);

-- ============================================================
-- 1. Helper Function: Parent Path Extractor
-- ============================================================
CREATE OR REPLACE FUNCTION get_parent_path(p_path TEXT) 
RETURNS TEXT AS $$
BEGIN
    -- Removes the last segment of the path (e.g., 'coding/web/react' -> 'coding/web')
    IF p_path IS NULL OR p_path = '' OR p_path !~ '/' THEN
        RETURN NULL;
    END IF;
    RETURN regexp_replace(p_path, '/[^/]+$', '');
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- ============================================================
-- 2. Trigger: Automatic Skill Linker
-- ============================================================
CREATE OR REPLACE FUNCTION trg_auto_link_skill_hierarchy() 
RETURNS TRIGGER AS $$
DECLARE
    v_parent_path TEXT;
    v_parent_id INTEGER;
BEGIN
    -- Get the parent path string
    v_parent_path := get_parent_path(NEW.path);

    IF v_parent_path IS NOT NULL THEN
        -- Find the ID of the parent skill in the database
        SELECT id INTO v_parent_id 
        FROM knowledge_skills 
        WHERE path = v_parent_path 
        LIMIT 1;

        -- If parent exists, create the relation
        IF v_parent_id IS NOT NULL THEN
            INSERT INTO entity_relations (
                source_entity_id, 
                source_entity_type, 
                target_entity_id, 
                target_entity_type, 
                relation_type, 
                weight
            )
            VALUES (
                NEW.id, 
                'skill', 
                v_parent_id, 
                'skill', 
                'PART_OF', 
                1.0
            )
            ON CONFLICT DO NOTHING;
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Register the trigger on knowledge_skills
DROP TRIGGER IF EXISTS trg_skill_hierarchy_linker ON knowledge_skills;
CREATE TRIGGER trg_skill_hierarchy_linker
AFTER INSERT OR UPDATE ON knowledge_skills
FOR EACH ROW EXECUTE FUNCTION trg_auto_link_skill_hierarchy();

-- ============================================================
-- 3. Stored Procedure: Fetch Recursive Inheritance Chain
-- ============================================================
-- This returns all instruction chunks from the skill up to the root
-- Used by the RAG engine to build the "System Prompt"
CREATE OR REPLACE FUNCTION get_skill_inheritance_chain(p_normalized_name TEXT)
RETURNS TABLE (
    skill_level INTEGER,
    skill_path TEXT,
    chunk_heading VARCHAR(512),
    chunk_content TEXT
) AS $$
BEGIN
    RETURN QUERY
    WITH RECURSIVE skill_tree AS (
        -- Base Case: The specific skill requested
        SELECT id, name, path, 1 as level
        FROM knowledge_skills
        WHERE normalized_name = p_normalized_name
        
        UNION ALL
        
        -- Recursive Case: Find the parent using the path
        SELECT s.id, s.name, s.path, st.level + 1
        FROM knowledge_skills s
        JOIN skill_tree st ON s.path = get_parent_path(st.path)
    )
    SELECT 
        st.level::INTEGER,
        st.path,
        sc.heading,
        sc.content
    FROM skill_tree st
    JOIN skill_chunks sc ON st.id = sc.skill_id
    WHERE sc.chunk_type = 'instructions'
    ORDER BY st.level DESC; -- root instructions first, leaf instructions last
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- Shared Context extensions on semantic_cache
-- ============================================================
ALTER TABLE semantic_cache ADD COLUMN IF NOT EXISTS shared_context JSONB;
ALTER TABLE semantic_cache ADD COLUMN IF NOT EXISTS content_hash TEXT;
ALTER TABLE semantic_cache ADD COLUMN IF NOT EXISTS is_current BOOLEAN DEFAULT TRUE;
ALTER TABLE semantic_cache ADD COLUMN IF NOT EXISTS hit_count INT DEFAULT 0;
ALTER TABLE semantic_cache ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_semantic_cache_lookup ON semantic_cache (query_hash, staleness_version);

-- ============================================================
-- Materialized View for Chunk Performance Scoring
-- ============================================================
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_chunk_performance AS
SELECT 
    ec.chunk_id,
    COUNT(DISTINCT ec.event_id) AS total_retrievals,
    COUNT(CASE WHEN af.quality_score >= 0.8 THEN 1 END) AS positive_feedback,
    COUNT(CASE WHEN af.is_negative = true THEN 1 END) AS negative_feedback,
    CASE 
        WHEN COUNT(DISTINCT ec.event_id) = 0 THEN 0.0
        ELSE (COUNT(CASE WHEN af.quality_score >= 0.8 THEN 1 END)::FLOAT - COUNT(CASE WHEN af.is_negative = true THEN 1 END)::FLOAT) / COUNT(DISTINCT ec.event_id)
    END AS chunk_performance_score
FROM event_chunks ec
LEFT JOIN audit_feedback af ON ec.event_id = af.retrieval_event_id
GROUP BY ec.chunk_id;

CREATE INDEX IF NOT EXISTS idx_mv_chunk_performance_score ON mv_chunk_performance (chunk_performance_score DESC);

-- ============================================================
-- RAG: Incremental Performance Tracking (Online RLHF)
-- ============================================================
CREATE TABLE IF NOT EXISTS chunk_stats (
    chunk_id UUID PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE,
    total_retrievals  INTEGER DEFAULT 0,
    positive_feedback INTEGER DEFAULT 0,
    negative_feedback INTEGER DEFAULT 0,
    performance_score FLOAT DEFAULT 0.0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Trigger to maintain chunk_stats from feedback loops
CREATE OR REPLACE FUNCTION update_chunk_performance_stats() RETURNS trigger AS $$
DECLARE
    v_chunk_id UUID;
    v_is_negative BOOLEAN;
    v_quality_score FLOAT;
BEGIN
    -- Get chunk_id from event_chunks based on retrieval_event_id
    FOR v_chunk_id IN SELECT chunk_id FROM event_chunks WHERE event_id = NEW.retrieval_event_id LOOP
        -- Upsert stats
        INSERT INTO chunk_stats (chunk_id, total_retrievals, positive_feedback, negative_feedback, performance_score)
        VALUES (v_chunk_id, 1, CASE WHEN NEW.quality_score >= 0.8 THEN 1 ELSE 0 END, CASE WHEN NEW.is_negative THEN 1 ELSE 0 END, 0.0)
        ON CONFLICT (chunk_id) DO UPDATE SET
            total_retrievals = chunk_stats.total_retrievals + 1,
            positive_feedback = chunk_stats.positive_feedback + CASE WHEN NEW.quality_score >= 0.8 THEN 1 ELSE 0 END,
            negative_feedback = chunk_stats.negative_feedback + CASE WHEN NEW.is_negative THEN 1 ELSE 0 END,
            performance_score = (chunk_stats.positive_feedback::FLOAT - chunk_stats.negative_feedback::FLOAT) / GREATEST(chunk_stats.total_retrievals, 1),
            updated_at = CURRENT_TIMESTAMP;
            
        UPDATE chunk_scores SET 
            performance_score = (chunk_stats.positive_feedback::FLOAT - chunk_stats.negative_feedback::FLOAT) / GREATEST(chunk_stats.total_retrievals, 1),
            feedback_count = chunk_stats.total_retrievals,
            updated_at = CURRENT_TIMESTAMP
        FROM chunk_stats
        WHERE chunk_scores.chunk_id = v_chunk_id AND chunk_stats.chunk_id = v_chunk_id;
        
        -- Insert if doesn't exist
        INSERT INTO chunk_scores (chunk_id, performance_score, feedback_count)
        SELECT v_chunk_id, performance_score, total_retrievals 
        FROM chunk_stats WHERE chunk_id = v_chunk_id
        ON CONFLICT (chunk_id) DO NOTHING;
    END LOOP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_audit_feedback_stats ON audit_feedback;
CREATE TRIGGER trg_audit_feedback_stats
AFTER INSERT ON audit_feedback
FOR EACH ROW EXECUTE FUNCTION update_chunk_performance_stats();

-- ============================================================
-- Partition Management Stored Procedure
-- ============================================================
CREATE OR REPLACE PROCEDURE manage_retrieval_partitions()
LANGUAGE plpgsql AS $$
DECLARE
    next_month TIMESTAMPTZ := date_trunc('month', now() + interval '1 month');
    partition_name_events TEXT;
    partition_name_chunks TEXT;
    start_date TEXT := to_char(next_month, 'YYYY_MM');
    end_date TEXT := to_char(next_month + interval '1 month', 'YYYY_MM');
BEGIN
    partition_name_events := 'retrieval_events_y' || start_date;
    partition_name_chunks := 'event_chunks_y' || start_date;
    
    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS %I PARTITION OF retrieval_events 
         FOR VALUES FROM (%L) TO (%L)',
        partition_name_events, 
        next_month, 
        next_month + interval '1 month'
    );

    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS %I PARTITION OF event_chunks 
         FOR VALUES FROM (%L) TO (%L)',
        partition_name_chunks, 
        next_month, 
        next_month + interval '1 month'
    );
END;
$$;
-- ============================================================
-- Agentic RL Router: Telemetry & Metrics
-- ============================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'hallucination_category') THEN
        CREATE TYPE hallucination_category AS ENUM ('none', 'type', 'timing', 'format', 'content');
    END IF;
END$$;


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

CREATE TABLE IF NOT EXISTS bandit_weights (
    id          SERIAL PRIMARY KEY,
    model_name  VARCHAR(64) NOT NULL UNIQUE,
    weights_bin BYTEA NOT NULL,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
