FROM python:3.11.9-slim-bookworm

RUN groupadd -g 1003 rluser && useradd -u 1003 -g rluser -m rluser
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libpq-dev gcc curl && rm -rf /var/lib/apt/lists/*
COPY rl_router/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy only the RL router source code
COPY --chown=rluser:rluser rl_router/ rl_router/
COPY --chown=rluser:rluser core/ core/

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

USER rluser
EXPOSE 8100

HEALTHCHECK --interval=10s --timeout=5s CMD curl -f http://localhost:8100/health || exit 1
CMD ["python", "-m", "uvicorn", "rl_router.server:app", "--host", "0.0.0.0", "--port", "8100"]
