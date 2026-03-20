FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for psycopg2
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY rl_router/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
# Note: We copy the entire project root as /app so that relative imports within rl_router work
# and the agentos-net can resolve things. However, we'll set PYTHONPATH.
COPY . .

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Expose the RL Router port
EXPOSE 8100

# Start the application
CMD ["python", "-m", "uvicorn", "rl_router.server:app", "--host", "0.0.0.0", "--port", "8100"]
