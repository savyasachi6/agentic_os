-- ============================================================
-- Seed Skill Relations based on embedding similarity
-- ============================================================

INSERT INTO skill_relations (source_skill_id, target_skill_id, relation_type, weight)
SELECT a.skill_id, b.skill_id, 'similar', MAX(1 - (a.embedding <=> b.embedding)) as sim
FROM skill_chunks a
JOIN skill_chunks b ON a.skill_id < b.skill_id
GROUP BY a.skill_id, b.skill_id
HAVING MAX(1 - (a.embedding <=> b.embedding)) > 0.85
ON CONFLICT DO NOTHING;
