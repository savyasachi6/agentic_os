-- Reclassify skills based on path patterns
UPDATE knowledge_skills SET skill_type = 'framework' WHERE path ILIKE '%coding%' OR path ILIKE '%web%' OR path ILIKE '%javascript%' OR path ILIKE '%frontend%';
UPDATE knowledge_skills SET skill_type = 'tool' WHERE path ILIKE '%tools%' OR path ILIKE '%scripts%' OR path ILIKE '%mcp%';
UPDATE knowledge_skills SET skill_type = 'rag' WHERE path ILIKE '%rag%' OR path ILIKE '%knowledge%' OR path ILIKE '%retrieval%';
UPDATE knowledge_skills SET skill_type = 'reinforcement_learning' WHERE path ILIKE '%reinforcement_learning%' OR path ILIKE '%bandit%' OR path ILIKE '%rl%';
UPDATE knowledge_skills SET skill_type = 'robotics' WHERE path ILIKE '%robotics%' OR path ILIKE '%ros%' OR path ILIKE '%isaac%' OR path ILIKE '%sim%';
UPDATE knowledge_skills SET skill_type = 'pattern' WHERE path ILIKE '%pattern%' OR path ILIKE '%design%' OR path ILIKE '%architecture%';
UPDATE knowledge_skills SET skill_type = 'ml' WHERE path ILIKE '%ml%' OR path ILIKE '%ai%' OR path ILIKE '%training%' OR path ILIKE '%embed%';

-- Default everything else to 'concept' if not matched (optional, but keep it as is if already concept)
-- UPDATE knowledge_skills SET skill_type = 'concept' WHERE skill_type NOT IN ('framework', 'tool', 'rag', 'reinforcement_learning', 'robotics', 'pattern', 'ml');
