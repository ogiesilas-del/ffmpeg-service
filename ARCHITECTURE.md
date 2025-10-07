# System Architecture

## Overview

This is a production-ready asynchronous video processing microservice that handles three main operations:
1. **Video Captioning** - AI-generated subtitles using OpenAI Whisper
2. **Video Merging** - Combining multiple scenes with voiceovers
3. **Background Music** - Adding background music to videos

## Architecture Diagram

```
┌─────────────────┐
│   Client App    │
└────────┬────────┘
         │
         │ HTTP REST API
         ▼
┌─────────────────────────────────────┐
│         FastAPI Web Server          │
│  ┌──────────────────────────────┐   │
│  │  POST /tasks/caption         │   │
│  │  POST /tasks/merge           │   │
│  │  POST /tasks/background-music│   │
│  │  GET  /tasks/{id}            │   │
│  │  GET  /video/{filename}      │   │
│  │  GET  /health                │   │
│  └──────────────────────────────┘   │
└──────────┬──────────────┬───────────┘
           │              │
           │              │
           ▼              ▼
    ┌──────────┐    ┌──────────┐
    │ Supabase │    │  Redis   │
    │ (Tasks)  │    │ (Queue)  │
    └──────────┘    └─────┬────┘
                          │
                          │ BRPOP (blocking)
                          ▼
                 ┌─────────────────┐
                 │ Worker Process  │
                 │  ┌───────────┐  │
                 │  │ Caption   │  │
                 │  │ Merge     │  │
                 │  │ Music     │  │
                 │  └───────────┘  │
                 └────────┬────────┘
                          │
                          ▼
                    ┌──────────┐
                    │ FFmpeg + │
                    │ Whisper  │
                    └─────┬────┘
                          │
                          ▼
                   ┌─────────────┐
                   │ videos/     │
                   │ folder      │
                   └─────────────┘
```

## Components

### 1. FastAPI Web Server (`app/main.py`)

**Purpose:** Handle HTTP requests and manage task submission

**Responsibilities:**
- Accept task submissions via REST API
- Validate input parameters and file sizes
- Create task records in Supabase
- Enqueue tasks to Redis
- Serve processed videos
- Provide health checks

**Key Features:**
- CORS middleware for cross-origin requests
- Request logging middleware
- Global exception handling
- Automatic OpenAPI documentation
- Lifespan events for service initialization

### 2. Worker Process (`worker.py`)

**Purpose:** Process video tasks asynchronously

**Responsibilities:**
- Poll Redis queue for new tasks
- Download videos and audio files
- Execute FFmpeg and Whisper operations
- Update task status in Supabase
- Clean up temporary files

**Key Features:**
- Graceful shutdown on SIGTERM/SIGINT
- Concurrent processing with semaphore
- Task type routing
- Comprehensive error handling
- Automatic retry on transient failures

### 3. Supabase Database

**Schema:**
```sql
tasks (
  id UUID PRIMARY KEY,
  task_type TEXT (caption|merge|background_music),
  status TEXT (queued|running|success|failed),
  video_url TEXT,
  model_size TEXT,
  result_video_url TEXT,
  error_message TEXT,
  file_size BIGINT,
  metadata JSONB,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ
)
```

**RLS Policies:**
- Allow public read for task status polling
- Allow public insert for task submission
- Allow public update for worker updates

### 4. Redis Task Queue

**Data Structures:**

**Queue (LIST):**
```
ffmpeg:queue = [
  {"task_id": "uuid", "task_type": "caption"},
  {"task_id": "uuid", "task_type": "merge"},
  ...
]
```

**Task Metadata (STRING with TTL):**
```
ffmpeg:task:{uuid} = {
  "task_id": "uuid",
  "task_type": "caption",
  "timestamp": "2025-10-07T12:00:00Z"
}
TTL: 7200 seconds (2 hours)
```

### 5. Services Layer

#### Redis Service (`app/services/redis_service.py`)
- Connection management with connection pooling
- Task enqueueing (LPUSH)
- Task dequeueing (BRPOP with timeout)
- Queue length monitoring
- Metadata storage with TTL

#### Supabase Service (`app/services/supabase_service.py`)
- Task CRUD operations
- Status updates with timestamps
- Query old tasks for cleanup
- Health checks

#### Cleanup Service (`app/services/cleanup_service.py`)
- Scheduled cleanup every hour
- Delete videos older than TTL
- Remove orphaned files
- Clean temporary directories

### 6. Utilities

#### File Utils (`utils/file_utils.py`)
- Async file download with progress
- File size validation (100MB limit)
- Filename security validation
- Disk space checks
- Temporary file cleanup

#### FFmpeg Utils (`utils/ffmpeg_utils.py`)
- Video duration detection
- SRT subtitle generation
- Subtitle burning with FFmpeg
- Video/audio merging
- Video concatenation
- Background music mixing

### 7. Task Processors (`workers/processors.py`)

#### Caption Processor
```python
1. Download video
2. Load Whisper model (small by default)
3. Transcribe audio → segments
4. Generate SRT with 3 words/line
5. Burn subtitles with FFmpeg
6. Save: {task_id}_captioned.mp4
```

#### Merge Processor
```python
1. Download all scenes and voiceovers in parallel
2. For each scene:
   - Scale video (cover or contain mode)
   - Adjust video volume (0.2)
   - Mix with voiceover (volume 2.0)
   - Save processed scene
3. Create concat file list
4. Concatenate all scenes
5. Save: {task_id}_merged.mp4
```

#### Background Music Processor
```python
1. Download video and music
2. Detect video duration with FFprobe
3. Loop music to match duration
4. Mix audio streams:
   - Video audio (volume 1.0)
   - Background music (volume 0.3)
5. Copy video stream (no re-encode)
6. Save: {task_id}_with_music.mp4
```

## Data Flow

### Task Submission Flow

```
1. Client → POST /tasks/caption
             ├─ Validate video_url
             ├─ Check file size (HEAD request)
             └─ If valid:
                 ├─ Insert into Supabase (status: queued)
                 ├─ Enqueue to Redis (ffmpeg:queue)
                 └─ Return task_id

2. Worker polls Redis (BRPOP 5s timeout)
   └─ If task found:
       ├─ Fetch full task data from Supabase
       ├─ Update status to "running"
       ├─ Process based on task_type
       └─ Update status to "success" or "failed"

3. Client → GET /tasks/{task_id}
             └─ Query Supabase
                 └─ Return status + video_url (if complete)

4. Client → GET /video/{filename}
             ├─ Validate filename pattern
             ├─ Check file exists
             └─ Stream video file
```

## Concurrency Model

### Web Server
- Asynchronous I/O with asyncio
- Multiple workers via Uvicorn
- Non-blocking file downloads
- Concurrent request handling

### Worker Process
- Single event loop per worker
- Semaphore limiting (3 concurrent tasks default)
- Blocking queue polling (BRPOP)
- Parallel downloads within tasks

### Scaling Strategy
```
Load Distribution:
├─ Web Server: Scale horizontally (multiple instances)
├─ Worker: Scale horizontally (multiple instances)
├─ Redis: Single instance (shared queue)
└─ Supabase: Managed (auto-scaling)

Concurrency Limits:
├─ MAX_CONCURRENT_WORKERS=3 per worker instance
├─ File downloads: Unlimited (async)
└─ FFmpeg processes: Limited by semaphore
```

## Error Handling

### Client Errors (4xx)
- **400 Bad Request**: Invalid URL, unreachable resource
- **404 Not Found**: Task or video not found
- **413 Payload Too Large**: File exceeds 100MB limit

### Server Errors (5xx)
- **500 Internal Server Error**: Database failures, Redis errors
- Task marked as "failed" with error_message
- Partial files cleaned up automatically

### Retry Strategy
- No automatic retries (client must resubmit)
- Idempotent operations (safe to retry)
- Failed tasks remain in database for debugging

## Security Considerations

### Input Validation
- URL format validation with Pydantic
- File size checks before download
- Filename whitelist pattern matching
- No directory traversal attacks

### Database Security
- Row Level Security (RLS) enabled
- Public policies for read-only access
- No sensitive data in public responses
- SQL injection prevention (parameterized queries)

### API Security
- CORS enabled (configurable origins)
- Rate limiting recommended (external)
- No authentication (add if needed)
- HTTPS enforced in production

### File Security
- Videos stored in isolated directory
- Automatic cleanup after TTL
- No user-provided filenames
- UUID-based naming scheme

## Performance Optimizations

### Caching
- Task status cached in Redis (10s)
- Whisper models cached on disk
- Video streaming with Range requests
- FFmpeg video stream copying (no re-encode)

### Resource Management
- Connection pooling (Redis)
- Disk space checks before processing
- Temporary file cleanup
- Memory-efficient streaming

### Processing Optimizations
- Parallel scene processing
- Concurrent downloads
- FFmpeg hardware acceleration (if available)
- Efficient video concatenation (copy codec)

## Monitoring and Observability

### Health Checks
```
GET /health
{
  "status": "healthy",
  "redis": "connected",
  "supabase": "connected",
  "queue_length": 5
}
```

### Logging
- Structured logs with timestamps
- Task ID context in all logs
- Request/response logging
- FFmpeg stderr capture

### Metrics (Recommended)
- Queue length
- Processing time per task type
- Success/failure rates
- Disk usage
- Memory usage

## Deployment Considerations

### Environment Variables
```
Required:
- VITE_SUPABASE_URL
- VITE_SUPABASE_ANON_KEY
- REDIS_URL

Optional:
- MAX_FILE_SIZE_MB (default: 100)
- MAX_CONCURRENT_WORKERS (default: 3)
- TASK_TTL_HOURS (default: 2)
```

### Resource Requirements
```
Web Server:
- CPU: 1 vCPU minimum
- RAM: 512MB minimum
- Disk: Ephemeral (no state)

Worker:
- CPU: 2+ vCPUs (FFmpeg intensive)
- RAM: 2GB+ (Whisper models)
- Disk: 10GB+ (videos + cache)
```

### Persistent Storage
- Videos stored in `VIDEO_OUTPUT_DIR`
- Whisper models in `WHISPER_MODEL_CACHE_DIR`
- Consider S3/R2 for production
- Automatic cleanup after TTL

## Future Enhancements

### Potential Improvements
1. Webhook notifications on task completion
2. Progress tracking (25%, 50%, 75% complete)
3. Video format conversion
4. Quality/resolution options
5. Authentication and user management
6. CDN integration for video serving
7. Video thumbnails generation
8. Batch processing API
9. Video analytics (duration, size, format)
10. Custom subtitle styling options
