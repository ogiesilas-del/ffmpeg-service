#!/bin/bash

echo "Starting FFmpeg Video Processing Microservice"
echo "=============================================="

mkdir -p /app/videos

echo "Verifying Whisper model cache..."
if [ -d "$HOME/.cache/whisper" ] && [ "$(ls -A $HOME/.cache/whisper)" ]; then
    echo "✅ Whisper model cache found"
else
    echo "⚠️  Whisper model cache not found, will download on first use"
fi

echo "Starting worker process..."
python worker.py &
WORKER_PID=$!
echo "Worker started with PID: $WORKER_PID"

echo "Starting web server on port $PORT..."
python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1 &
WEB_PID=$!
echo "Web server started with PID: $WEB_PID"

trap "echo 'Shutting down...'; kill $WORKER_PID $WEB_PID; exit" SIGINT SIGTERM

wait
