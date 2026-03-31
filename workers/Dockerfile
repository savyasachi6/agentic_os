FROM python:3.11.9-slim-bookworm

RUN groupadd -g 1005 workeruser && useradd -u 1005 -g workeruser -m workeruser
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    postgresql-client \
    redis-tools \
    nodejs \
    npm \
    libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy necessary components for background execution
COPY --chown=workeruser:workeruser core/ core/
COPY --chown=workeruser:workeruser agents/ agents/
COPY --chown=workeruser:workeruser tools/ tools/
COPY --chown=workeruser:workeruser rag/ rag/
COPY --chown=workeruser:workeruser db/ db/
COPY --chown=workeruser:workeruser productivity/ productivity/
COPY --chown=workeruser:workeruser prompts/ prompts/
COPY --chown=workeruser:workeruser constants/ constants/
COPY --chown=workeruser:workeruser rl_router/ rl_router/
COPY --chown=workeruser:workeruser workers/ workers/
COPY --chown=workeruser:workeruser entrypoint.sh .
RUN chmod +x entrypoint.sh && chown workeruser:workeruser entrypoint.sh

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

USER workeruser

# Verify Redis heartbeat key from orchestrator logic
HEALTHCHECK --interval=30s --timeout=10s CMD redis-cli -a $$(cat /run/secrets/redis_password) ping || exit 1

ENTRYPOINT ["/bin/bash", "./entrypoint.sh"]
CMD ["python", "-m", "workers.worker_manager"]
