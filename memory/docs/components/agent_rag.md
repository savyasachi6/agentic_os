# Component: Agent RAG (Knowledge)

## Responsibility

The `agent_rag` component manages the ingestion and retrieval of unstructured knowledge. It enables the agent to "read" local documentation and codebases to fulfill complex user requests accurately.

## Key Submodules

### [Ingestion Pipeline](file:///c:/Users/savya/projects/agentic_os/memory/agent_rag/ingestion)

Handles the crawling and parsing of local folders. It includes strategies for:

- **Markdown Parsing**: Preserving headers and structural context.
- **Code Indexing**: Identifying function and class boundaries.
- **Chunking**: Overlapping fixed-size or structure-aware windows.

### [Retrieval Logic](file:///c:/Users/savya/projects/agentic_os/memory/agent_rag/retrieval)

The query interface. It generates embeddings for user questions and performs similarity searches against the `docs` table. It includes support for **re-ranking** and **multi-stage retrieval**.

## Integration

RAG is triggered by the `rag_query` tool in the Core's registry. The retrieval results are formatted into a compressed context block and injected into the LLM system prompt.
