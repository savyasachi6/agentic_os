-- ============================================================
-- Seed Skill Relations based on embedding similarity
-- ============================================================

INSERT INTO skill_relations (source_skill_id, target_skill_id, relation_type, weight)
SELECT 
    sc1.skill_id, 
    sc2.skill_id, 
    'RELATED_TO', 
    1 - (sc1.embedding <=> sc2.embedding)
FROM skill_chunks sc1
JOIN skill_chunks sc2 ON sc1.skill_id < sc2.skill_id
WHERE 1 - (sc1.embedding <=> sc2.embedding) > 0.75
ON CONFLICT DO NOTHING;

-- Also link skills that share the same path hierarchy (Parent/Child)
-- This is partially handled by the trigger but good to have a batch seed
INSERT INTO skill_relations (source_skill_id, target_skill_id, relation_type, weight)
SELECT 
    s1.id as source_skill_id,
    s2.id as target_skill_id,
    'PART_OF',
    1.0
FROM knowledge_skills s1
JOIN knowledge_skills s2 ON s1.path LIKE s2.path || '/%'
WHERE s1.id != s2.id
ON CONFLICT DO NOTHING;
