# Developer Onboarding: Agentic Memory & Fractal RAG

Welcome to the memory core of Agentic OS. This guide explains how to navigate and maintain the high-complexity PostgreSQL cognitive layer.

## 1. High-Fidelity Ingestion (Docling Integration)

We use **Docling** for structured document parsing. This is mandatory for complex PDFs/DOCX with tables.

### Setup Instructions

1. **Install Docling:**

   ```bash
   pip install docling langchain-docling
   ```

   > [!NOTE]
   > This will install `torch` and other ML dependencies. Ensure you have ~2GB free space.

2. **Environment Variables (`.env`):**

   ```bash
   DOCLING_CHUNK_SIZE=1024
   DOCLING_TOKENIZER=BAAI/bge-small-en-v1.5
   DOCLING_USE_OCR=true
   ```

## 2. The Recursive Reasoning Engine (`nodes` table)

The `nodes` table is designed to store recursive "Tree of Thought" (ToT) logs.

- **Fractal Depth:** Use the `fractal_depth` column to visualize nested logical calls. A `fractal_depth` of 0 is the root plan; deeper levels represent sub-agent delegated tasks.
- **Traceability:** Every node has a `parent_id`. To visualize a reasoning chain, perform a recursive CTE or use the optimized `idx_nodes_fractal` index.
- **Embedding Search:** Reason slices are embedded. You can find "similar reasoning paths" from past successful turns by querying `nodes` with `vector_cosine_ops`.

---

## 3. Dealing with Scaling & Maintenance

### Partition Management

Logs grow fast. We use range partitioning by month on `retrieval_events` and `event_chunks`.

- **Manual Trigger:** Run `CALL manage_retrieval_partitions();` in SQL.
- **Automation:** Use the provided [partition_manager.py](file:///c:/Users/savya/projects/agentic_os/agentos_memory/agent_memory/partition_manager.py) script.

#### Setting up Automation (Cron)

1. Ensure `psycopg` is installed: `pip install psycopg`
2. Configure environment variables (`DB_NAME`, `DB_USER`, etc.).
3. Add to crontab (25th of every month at midnight):

   ```bash
   0 0 25 * * /usr/bin/python3 /path/to/agentos_memory/agent_memory/partition_manager.py
   ```

- **Retention:** To purge logs older than 6 months, simply `DROP TABLE retrieval_events_yYYYY_MM`. It's O(1).

### Materialized Views

Long-term performance analytics are stored in `mv_chunk_performance`.

- **Refreshes:** Run `REFRESH MATERIALIZED VIEW CONCURRENTLY mv_chunk_performance;` during off-peak hours.
- **Constraint:** You must have a unique index on the MV for concurrent refreshes to work.

---

## 4. Key Performance Tuning

If retrieval slows down:

1. **Check HNSW Stats:** `SELECT * FROM pg_vector_index_stat;`
2. **Planner Optimization:** Ensure `enable_partitionwise_join` is `on` in Postgres configuration.
3. **Vacuuming:** Autovacuum should be aggressive on `chunk_scores` due to frequent updates, but `chunk_embeddings` should remain static (immutable) to keep the index clean.
