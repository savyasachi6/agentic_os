FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all application code (monorepo structure)
COPY . .

# Expose server port
EXPOSE 8000

# Start indexer in the background, then launch the server immediately
CMD ["sh", "-c", "python agent_core/main.py index & python agent_core/main.py serve --host 0.0.0.0 --port 8000"]
