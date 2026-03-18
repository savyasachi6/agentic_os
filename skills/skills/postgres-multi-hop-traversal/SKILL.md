# postgres-multi-hop-traversal

Execute multi-hop relationship discovery and pathfinding using SQL recursive CTEs.

## Instructions

# Graph-Based Reasoning in Postgres

To perform graph-based reasoning in a relational database, you must treat entity tables as nodes and join tables or foreign keys as edges. This skill focuses on traversing these connections across multiple 'hops' to find indirect relationships.

### Step 1: Map the Schema
Identify which tables represent nodes (e.g., `Users`, `Products`) and which represent edges (e.g., `Follows`, `Purchased`). In a unified knowledge base, you might find a generic `edges` table with `subject_id`, `predicate`, and `object_id` columns.

### Step 2: Fixed-Hop Traversal
For a known number of steps (e.g., 'Friends of Friends'), use standard inner joins. 

**Example (2-Hop):**
```sql
SELECT e2.target_id
FROM edges e1
JOIN edges e2 ON e1.target_id = e2.source_id
WHERE e1.source_id = 'entity_a' AND e1.type = 'friend';
```

### Step 3: N-Hop Traversal with Recursive CTEs
When the path length is variable or unknown, use a Recursive Common Table Expression (CTE). 

1. **Anchor Member**: Define the starting node(s).
2. **Recursive Member**: Join the previous result set back to the edges table.
3. **Cycle Prevention**: Maintain a path array to ensure you don't visit the same node twice.

**Example (Recursive Pathfinding):**
```sql
WITH RECURSIVE search_graph AS (
    SELECT target_id, 1 AS depth, ARRAY[source_id, target_id] AS path
    FROM edges
    WHERE source_id = 'start_node'
  UNION ALL
    SELECT e.target_id, sg.depth + 1, sg.path || e.target_id
    FROM edges e
    JOIN search_graph sg ON e.source_id = sg.target_id
    WHERE sg.depth < 5 AND NOT (e.target_id = ANY(sg.path))
)
SELECT * FROM search_graph;
```

### Best Practices
- **Depth Limits**: Always include a depth constraint (e.g., `depth < 10`) to prevent runaway queries on highly connected graphs.
- **Indexing**: Ensure `source_id` and `target_id` (or equivalent FKs) are indexed to prevent full table scans during recursion.
- **Filtering**: Apply filters (like relationship types) as early as possible in the anchor or recursive member to reduce the search space.