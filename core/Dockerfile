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

# Run the indexer followed by the FastAPI server
CMD ["sh", "-c", "python main.py index && python main.py server --host 0.0.0.0 --port 8000"]
