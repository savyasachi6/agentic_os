FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install root project dependencies first
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install UI-specific dependencies
COPY ui/requirements.txt ui-requirements.txt
RUN pip install --no-cache-dir -r ui-requirements.txt

# Copy all application code (monorepo structure)
COPY . .

# Ensure all project packages are importable
ENV PYTHONPATH=/app

# Expose Streamlit port
EXPOSE 8501

# Run Streamlit — we run from /app so sys.path resolution works correctly
CMD ["streamlit", "run", "ui/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
