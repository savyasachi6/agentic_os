FROM python:3.11.9-slim-bookworm

RUN groupadd -g 1004 uiuser && useradd -u 1004 -g uiuser -m uiuser
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc curl postgresql-client && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
COPY ui/requirements.txt ui-requirements.txt
RUN pip install --no-cache-dir -r requirements.txt -r ui-requirements.txt

COPY --chown=uiuser:uiuser ui/ ui/
COPY --chown=uiuser:uiuser core/ core/
COPY --chown=uiuser:uiuser db/ db/
COPY --chown=uiuser:uiuser rag/ rag/
COPY --chown=uiuser:uiuser entrypoint.sh .
RUN chmod +x entrypoint.sh && chown uiuser:uiuser entrypoint.sh

RUN mkdir -p /home/uiuser/.streamlit && chown -R uiuser:uiuser /home/uiuser/.streamlit
# Copy hardened Streamlit Config
COPY --chown=uiuser:uiuser ui/config.toml /home/uiuser/.streamlit/config.toml

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

USER uiuser
EXPOSE 8501

HEALTHCHECK --interval=10s --timeout=5s CMD curl -f http://localhost:8501 || exit 1
ENTRYPOINT ["/bin/bash", "./entrypoint.sh"]
CMD ["streamlit", "run", "ui/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
