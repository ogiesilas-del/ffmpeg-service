#!/bin/bash

echo "🎬 FFmpeg Video Processing Microservice"
echo "========================================"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed"
    exit 1
fi

echo "✅ Python 3 found: $(python3 --version)"

# Check FFmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo "❌ FFmpeg is not installed"
    echo "Install with: sudo apt install ffmpeg (Ubuntu) or brew install ffmpeg (Mac)"
    exit 1
fi

echo "✅ FFmpeg found: $(ffmpeg -version | head -1)"

# Check Redis
if ! command -v redis-cli &> /dev/null; then
    echo "⚠️  Redis CLI not found. Make sure Redis server is running."
else
    echo "✅ Redis found"
fi

# Check .env file
if [ ! -f .env ]; then
    echo "⚠️  .env file not found. Copying from .env.example"
    cp .env.example .env
    echo "⚠️  Please edit .env with your credentials"
fi

# Create directories
mkdir -p videos whisper_cache

echo ""
echo "📦 Installing Python dependencies..."
pip3 install -r requirements.txt

echo ""
echo "🚀 Starting services..."
echo ""
echo "Choose an option:"
echo "1) Start Web Server only"
echo "2) Start Worker only"
echo "3) Start both (requires tmux or run in separate terminals)"
echo ""
read -p "Enter choice [1-3]: " choice

case $choice in
    1)
        echo "Starting web server on port 8000..."
        python3 -m uvicorn app.main:app --reload --port 8000
        ;;
    2)
        echo "Starting worker..."
        python3 worker.py
        ;;
    3)
        if command -v tmux &> /dev/null; then
            echo "Starting both services in tmux..."
            tmux new-session -d -s ffmpeg-api "python3 -m uvicorn app.main:app --reload --port 8000"
            tmux split-window -h -t ffmpeg-api "python3 worker.py"
            tmux attach -t ffmpeg-api
        else
            echo "tmux not found. Starting web server only."
            echo "Run 'python3 worker.py' in another terminal."
            python3 -m uvicorn app.main:app --reload --port 8000
        fi
        ;;
    *)
        echo "Invalid choice"
        exit 1
        ;;
esac
