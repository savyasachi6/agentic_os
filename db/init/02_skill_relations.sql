-- Skill relationship graph for relational RAG traversal.
-- Populated automatically by the skill indexer when it detects
-- that one skill imports, calls, or references another.

CREATE TABLE IF NOT EXISTS skill_relations (
    source_skill_id INTEGER NOT NULL
        REFERENCES knowledge_skills(id) ON DELETE CASCADE,
    target_skill_id INTEGER NOT NULL
        REFERENCES knowledge_skills(id) ON DELETE CASCADE,
    relation_type   VARCHAR(50) NOT NULL DEFAULT 'composes',
    -- composes  : source is built on top of target
    -- requires  : source needs target to function
    -- extends   : source is a specialization of target
    -- similar   : semantically related, no dependency
    weight          FLOAT NOT NULL DEFAULT 1.0,
    PRIMARY KEY (source_skill_id, target_skill_id)
);

CREATE INDEX IF NOT EXISTS idx_skill_relations_source
    ON skill_relations(source_skill_id);
CREATE INDEX IF NOT EXISTS idx_skill_relations_target
    ON skill_relations(target_skill_id);
