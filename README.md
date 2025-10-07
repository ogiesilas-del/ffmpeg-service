# FFmpeg Video Processing Microservice

A production-ready asynchronous video processing API built with FastAPI, Redis, and Supabase.

## Features

- **Video Captioning**: Add AI-generated subtitles using OpenAI Whisper
- **Video Merging**: Combine multiple video scenes with voiceovers
- **Background Music**: Add background music to videos with volume control
- **Asynchronous Processing**: Non-blocking task queue with Redis
- **File Size Limits**: 100MB per file with configurable limits
- **Automatic Cleanup**: Videos expire after 2 hours
- **Health Monitoring**: Built-in health checks and metrics

## Architecture

### Two-Process Design

1. **Web Server** (`app/main.py`): FastAPI application handling HTTP requests
2. **Worker Process** (`worker.py`): Background worker processing video tasks

### Data Flow

```
Client → POST /tasks/caption → Task stored in Supabase → Enqueued in Redis
                                                              ↓
                                          Worker polls Redis queue
                                                              ↓
                                          Process video with FFmpeg/Whisper
                                                              ↓
                                          Save to videos/ folder
                                                              ↓
Client ← GET /video/{filename} ← Update Supabase ← Complete task
```

## API Endpoints

### Task Submission

#### Caption Task
```bash
POST /tasks/caption
{
  "video_url": "https://example.com/video.mp4",
  "model_size": "small"
}
```

#### Merge Task
```bash
POST /tasks/merge
{
  "scene_clip_urls": ["https://example.com/scene1.mp4", "https://example.com/scene2.mp4"],
  "voiceover_urls": ["https://example.com/voice1.mp3", "https://example.com/voice2.mp3"],
  "width": 1080,
  "height": 1920,
  "video_volume": 0.2,
  "voiceover_volume": 2.0
}
```

#### Background Music Task
```bash
POST /tasks/background-music
{
  "video_url": "https://example.com/video.mp4",
  "music_url": "https://example.com/music.mp3",
  "music_volume": 0.3,
  "video_volume": 1.0
}
```

### Task Status

```bash
GET /tasks/{task_id}

Response:
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "success",
  "video_url": "https://your-app.railway.app/video/550e8400-..._captioned.mp4",
  "error": null,
  "created_at": "2025-10-07T12:00:00Z",
  "updated_at": "2025-10-07T12:05:00Z",
  "completed_at": "2025-10-07T12:05:00Z"
}
```

### Video Serving

```bash
GET /video/{filename}
```

### Health Check

```bash
GET /health

Response:
{
  "status": "healthy",
  "redis": "connected",
  "supabase": "connected",
  "queue_length": 5
}
```

## Environment Variables

Create a `.env` file:

```bash
# Supabase Configuration
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=your-anon-key

# Redis Configuration
REDIS_URL=redis://localhost:6379

# Application Configuration
PORT=8000
RAILWAY_PUBLIC_URL=https://your-app.railway.app
MAX_FILE_SIZE_MB=100
MAX_CONCURRENT_WORKERS=3
TASK_TTL_HOURS=2
VIDEO_OUTPUT_DIR=./videos
WHISPER_MODEL_CACHE_DIR=./whisper_cache
```

## Local Development

### Prerequisites

- Python 3.9+
- FFmpeg installed
- Redis server running
- Supabase account

### Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Run database migrations (already applied)
# Tables are created automatically in Supabase

# Start the web server
uvicorn app.main:app --reload --port 8000

# Start the worker (in a separate terminal)
python worker.py
```

### Testing

```bash
# Test caption endpoint
curl -X POST "http://localhost:8000/tasks/caption" \
  -H "Content-Type: application/json" \
  -d '{"video_url": "https://example.com/video.mp4", "model_size": "small"}'

# Check task status
curl "http://localhost:8000/tasks/{task_id}"

# Download processed video
curl "http://localhost:8000/video/{task_id}_captioned.mp4" -o output.mp4
```

## Railway Deployment

### Setup

1. Connect your GitHub repository to Railway
2. Add a Redis service to your project
3. Configure environment variables in Railway dashboard
4. Deploy both services:
   - **Web**: Uses `Procfile` web command
   - **Worker**: Uses `Procfile` worker command

### Environment Variables (Railway)

Set these in Railway dashboard:

```
VITE_SUPABASE_URL=<your-supabase-url>
VITE_SUPABASE_ANON_KEY=<your-supabase-key>
REDIS_URL=${{Redis.REDIS_URL}}
RAILWAY_PUBLIC_URL=${{RAILWAY_PUBLIC_DOMAIN}}
MAX_FILE_SIZE_MB=100
MAX_CONCURRENT_WORKERS=3
TASK_TTL_HOURS=2
```

### Scaling

- **Web Service**: Can scale horizontally (multiple instances)
- **Worker Service**: Can scale horizontally (multiple workers)
- **Redis**: Single instance shared across all services

## Project Structure

```
.
├── app/
│   ├── __init__.py
│   ├── config.py              # Configuration management
│   ├── main.py                # FastAPI application
│   ├── models/
│   │   ├── __init__.py
│   │   └── task.py            # Pydantic models
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── tasks.py           # Task endpoints
│   │   └── videos.py          # Video serving
│   └── services/
│       ├── __init__.py
│       ├── redis_service.py   # Redis queue management
│       ├── supabase_service.py # Database operations
│       └── cleanup_service.py # Cleanup scheduler
├── workers/
│   ├── __init__.py
│   └── processors.py          # Task processors
├── utils/
│   ├── __init__.py
│   ├── file_utils.py          # File operations
│   └── ffmpeg_utils.py        # FFmpeg wrappers
├── videos/                    # Output directory
├── worker.py                  # Worker entry point
├── requirements.txt
├── Procfile                   # Railway process definition
├── nixpacks.toml             # Railway build config
├── railway.json              # Railway deployment config
├── .env                      # Environment variables
└── README.md
```

## Task Processing Logic

### Caption Task
1. Download video from URL
2. Transcribe audio with Whisper
3. Generate SRT subtitles (max 3 words per line)
4. Burn subtitles into video with FFmpeg
5. Save as `{task_id}_captioned.mp4`

### Merge Task
1. Download all scene videos and voiceovers in parallel
2. For each scene:
   - Scale/crop video to target dimensions
   - Mix video audio with voiceover
   - Adjust volumes
3. Concatenate all processed scenes
4. Save as `{task_id}_merged.mp4`

### Background Music Task
1. Download video and music file
2. Detect video duration
3. Loop background music to match duration
4. Mix audio streams with specified volumes
5. Save as `{task_id}_with_music.mp4`

## Cleanup and Maintenance

- **Automatic Cleanup**: Runs every hour
- **Video Expiration**: 2 hours after completion
- **Orphaned File Removal**: Deletes files without database records
- **Temp File Cleanup**: Removes temp files older than 3 hours

## Security Features

- File size validation (100MB limit per file)
- Filename validation to prevent directory traversal
- Row Level Security (RLS) in Supabase
- Input validation with Pydantic models
- Error sanitization in API responses

## Monitoring

- Health check endpoint: `/health`
- Request logging middleware
- Task-specific logging with task_id context
- FFmpeg stderr capture for debugging

## Troubleshooting

### Worker not processing tasks
- Check Redis connection: `redis-cli ping`
- Check worker logs for errors
- Verify Supabase connection

### Videos not found
- Check `videos/` directory exists
- Verify RAILWAY_PUBLIC_URL is set correctly
- Check task status for completion

### FFmpeg errors
- Ensure FFmpeg is installed: `ffmpeg -version`
- Check disk space availability
- Review FFmpeg stderr in logs

## License

MIT
