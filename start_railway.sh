#!/bin/bash

echo "Starting FFmpeg Video Processing Microservice"
echo "=============================================="

mkdir -p videos whisper_cache

echo "Starting worker process..."
python worker.py &
WORKER_PID=$!
echo "Worker started with PID: $WORKER_PID"

echo "Starting web server on port $PORT..."
python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT &
WEB_PID=$!
echo "Web server started with PID: $WEB_PID"

trap "echo 'Shutting down...'; kill $WORKER_PID $WEB_PID; exit" SIGINT SIGTERM

wait
