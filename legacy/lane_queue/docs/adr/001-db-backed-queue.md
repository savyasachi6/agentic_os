# ADR 001: Postgres-Backed Command Queue

## Status

Accepted

## Context

Agent actions (LLM reasonings and side-effect tools) have historically been executed synchronously. This led to blocking event loops, complicated failure recovery, and made it impossible to share a batched execution engine across multiple tasks efficiently. We need a way to orchestrate multi-agent multi-task streams robustly without bringing in external massive dependencies like Kafka, Redis, or RabbitMQ.

## Decision

We chose a PostgreSQL DB-backed queue pattern leveraging `FOR UPDATE SKIP LOCKED`.

1. **Why Postgres?**: We already mandate Postgres to run the Agent (for `pgvector` RAG). Using it as our message broker introduces exactly 0 new infrastructure dependencies.
2. **Why Skip Locked?**: It enables multiple worker threads to pull from the same table without deadlocking or blocking each other on row locks, ensuring high transactional throughput for our scale point.
3. **Strict Order**: A `lane_id` and `seq` (sequence) field guarantee that commands in the same lane never parallelize; they remain perfectly linear, preserving the continuity of ReAct streams.

## Consequences

- Requires persistent PostgreSQL connection pooling.
- A slight latency hit (a few milliseconds) compared to in-memory processing, but entirely negligible compared to LLM generation times.
- Enables fault-tolerance out of the box; if a worker crashes, the DB row can be manually or chron-reset to `PENDING`.
