# API Reference — Agent Skills

## `agent_skills.indexer`

### `SkillIndexer(skills_dir: str = None)`

Initializes the indexer. `skills_dir` defaults to project config.

### `index_all()`

Scans the entire skills directory and syncs all valid Upskill packages to the vector store.

### `index_skill(skill_name: str) -> bool`

Force re-indexing of a single specific skill.

### `chunk_markdown(content: str, min_tokens=500, max_tokens=800) -> List[Dict]`

Low-level utility that splits Markdown by H2/H3 headers, merging small segments and splitting oversized ones.

---

## `agent_skills.retriever`

### `SkillRetriever()`

Initializes the retriever. Connects to the default `VectorStore`.

### `retrieve_context(user_utterance: str, session_id: str, top_k: int = 5) -> str`

The primary method for getting RAG results.

- **user_utterance**: The raw user request.
- **session_id**: Used to retrieve session-specific prior reasoning.
- **top_k**: Number of distinct skills to fetch.

**Returns**: A single Markdown-formatted string containing the retrieved skill instructions.

---

## `agent_skills.upskill`

### `load_metadata(skill_path: str) -> Dict`

Standard implementation for loading skill configurations. Supports both `plugin.json` and `skill_meta.json`.
