#!/bin/bash
# Agentic OS - Global Entrypoint Script
# Handles synchronization and signal forwarding.

set -e

# Helper to wait for a service to be ready
wait_for() {
    local host="$1"
    local port="$2"
    local name="$3"
    echo "Checking $name connectivity at $host:$port..."
    until pg_isready -h "$host" -p "$port"; do
        echo "Waiting for $name ($host:$port)..."
        sleep 2
    done
    echo "$name is ready!"
}

# If Postgres is defined in the environment, wait for it
if [ -n "$POSTGRES_HOST" ]; then
    wait_for "$POSTGRES_HOST" "5432" "PostgreSQL"
fi

# Execute the main container process (passed via CMD/ENTRYPOINT)
echo "Starting application..."
exec "$@"
