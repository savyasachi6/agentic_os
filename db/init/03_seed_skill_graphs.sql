-- ============================================================
-- Seed Skill Relations based on embedding similarity
-- ============================================================

INSERT INTO skill_relations (source_skill_id, target_skill_id, relation_type, weight)
SELECT a.id, b.id, 'similar', 1 - (a.embedding <=> b.embedding)
FROM knowledge_skills a CROSS JOIN knowledge_skills b
WHERE a.id < b.id
  AND 1 - (a.embedding <=> b.embedding) > 0.75
ON CONFLICT DO NOTHING;
