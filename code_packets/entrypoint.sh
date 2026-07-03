#!/bin/bash
set -e

echo "Starting Quantum Communication Gateway (QCG)..."

# Ensure log directory exists
mkdir -p logs

# Handle graceful shutdown
cleanup() {
    echo "Shutting down QCG gracefully..."
    kill -TERM "$child" 2>/dev/null
    wait "$child"
}

trap cleanup SIGINT SIGTERM

# Start FastAPI server via Uvicorn
uvicorn web_server:app --host 0.0.0.0 --port 8080 --workers 2 &
child=$!

echo "QCG is ready and accepting requests."
wait "$child"
