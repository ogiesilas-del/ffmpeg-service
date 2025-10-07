from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import logging
import time
from contextlib import asynccontextmanager
from app.config import settings
from app.services.redis_service import redis_service
from app.services.supabase_service import supabase_service
from app.routers import tasks, videos
from app.models.task import HealthCheckResponse

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    logger.info("Starting FastAPI application...")

    redis_connected = False
    supabase_connected = False

    try:
        settings.validate_config()
        logger.info("Configuration validated")
    except Exception as e:
        logger.warning(f"Configuration validation failed: {e}")

    try:
        supabase_service.connect()
        if supabase_service.client:
            supabase_connected = True
            logger.info("Supabase connected successfully")
    except Exception as e:
        logger.warning(f"Supabase connection failed: {e}")
        supabase_connected = False

    try:
        await redis_service.connect()
        logger.info("Redis connected successfully")
        redis_connected = True
    except Exception as e:
        logger.warning(f"Redis connection failed: {e}")
        redis_connected = False

    if redis_connected and supabase_connected:
        logger.info("All services connected successfully")
    else:
        logger.warning(f"Running with limited functionality - Redis: {redis_connected}, Supabase: {supabase_connected}")

    yield

    logger.info("Shutting down FastAPI application...")
    if redis_connected:
        await redis_service.disconnect()


app = FastAPI(
    title="FFmpeg Video Processing API",
    description="Asynchronous video processing microservice with captioning, merging, and background music",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all HTTP requests"""
    start_time = time.time()

    response = await call_next(request)

    duration = time.time() - start_time
    logger.info(
        f"{request.method} {request.url.path} - "
        f"Status: {response.status_code} - "
        f"Duration: {duration:.2f}s"
    )

    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled errors"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"}
    )


app.include_router(tasks.router)
app.include_router(videos.router)


@app.get("/", response_class=HTMLResponse)
async def root():
    """Root endpoint with API documentation and test form"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>FFmpeg Video Processing API</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                max-width: 900px;
                margin: 50px auto;
                padding: 20px;
                background-color: #f5f5f5;
            }
            h1 {
                color: #333;
            }
            .card {
                background: white;
                padding: 20px;
                margin: 20px 0;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            .endpoint {
                background: #e8f4f8;
                padding: 10px;
                margin: 10px 0;
                border-left: 4px solid #0066cc;
            }
            code {
                background: #f0f0f0;
                padding: 2px 6px;
                border-radius: 3px;
                font-family: monospace;
            }
            .button {
                background: #0066cc;
                color: white;
                padding: 10px 20px;
                border: none;
                border-radius: 5px;
                cursor: pointer;
                text-decoration: none;
                display: inline-block;
            }
            .button:hover {
                background: #0052a3;
            }
        </style>
    </head>
    <body>
        <h1>🎬 FFmpeg Video Processing API</h1>

        <div class="card">
            <h2>Welcome to the Video Processing Microservice</h2>
            <p>This API provides asynchronous video processing with three main operations:</p>
            <ul>
                <li><strong>Captioning:</strong> Add AI-generated subtitles using Whisper</li>
                <li><strong>Merging:</strong> Combine multiple video scenes with voiceovers</li>
                <li><strong>Background Music:</strong> Add background music to videos</li>
            </ul>
        </div>

        <div class="card">
            <h2>📚 API Endpoints</h2>

            <div class="endpoint">
                <strong>POST /tasks/caption</strong><br>
                Submit a video for captioning<br>
                Body: <code>{"video_url": "...", "model_size": "small"}</code>
            </div>

            <div class="endpoint">
                <strong>POST /tasks/merge</strong><br>
                Merge multiple videos with voiceovers<br>
                Body: <code>{"scene_clip_urls": [...], "voiceover_urls": [...]}</code>
            </div>

            <div class="endpoint">
                <strong>POST /tasks/background-music</strong><br>
                Add background music to a video<br>
                Body: <code>{"video_url": "...", "music_url": "..."}</code>
            </div>

            <div class="endpoint">
                <strong>GET /tasks/{task_id}</strong><br>
                Poll task status and get result URL
            </div>

            <div class="endpoint">
                <strong>GET /video/{filename}</strong><br>
                Stream/download processed video
            </div>

            <div class="endpoint">
                <strong>GET /health</strong><br>
                Check API health status
            </div>
        </div>

        <div class="card">
            <h2>📖 Documentation</h2>
            <p>
                <a href="/docs" class="button">Interactive API Docs (Swagger)</a>
                <a href="/redoc" class="button">API Documentation (ReDoc)</a>
            </p>
        </div>

        <div class="card">
            <h2>🔧 Usage Example</h2>
            <pre><code># Submit a caption task
curl -X POST "http://localhost:8000/tasks/caption" \\
  -H "Content-Type: application/json" \\
  -d '{"video_url": "https://example.com/video.mp4", "model_size": "small"}'

# Response: {"task_id": "...", "status": "queued", "message": "..."}

# Poll for status
curl "http://localhost:8000/tasks/{task_id}"

# When status is "success", download the video
curl "http://localhost:8000/video/{task_id}_captioned.mp4" -o output.mp4
</code></pre>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@app.get("/health", response_model=HealthCheckResponse)
async def health_check():
    """
    Health check endpoint

    Returns the health status of all services:
    - Overall API status
    - Redis connection status
    - Supabase connection status
    - Current queue length
    """
    redis_status = "connected" if await redis_service.is_healthy() else "disconnected"
    supabase_status = "connected" if supabase_service.is_healthy() else "disconnected"
    queue_length = await redis_service.get_queue_length()

    overall_status = "healthy" if (redis_status == "connected" and supabase_status == "connected") else "degraded"

    return HealthCheckResponse(
        status=overall_status,
        redis=redis_status,
        supabase=supabase_status,
        queue_length=queue_length
    )


@app.get("/debug/queue")
async def debug_queue_status():
    """
    Get detailed queue and system status for debugging
    """
    try:
        queue_length = await redis_service.get_queue_length()
        redis_healthy = await redis_service.is_healthy()
        supabase_healthy = supabase_service.is_healthy()

        logger.info(f"Debug endpoint called - Redis: {redis_healthy}, Supabase: {supabase_healthy}, Queue: {queue_length}")

        return {
            "redis": {
                "connected": redis_healthy,
                "queue_length": queue_length
            },
            "supabase": {
                "connected": supabase_healthy
            },
            "message": "Queue status retrieved"
        }
    except Exception as e:
        logger.error(f"Error getting debug info: {e}", exc_info=True)
        return {
            "error": str(e),
            "message": "Failed to retrieve queue status"
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.port)
