# Deployment Guide

## Railway Deployment

### Prerequisites

1. Railway account (https://railway.app)
2. GitHub repository with this code
3. Supabase account (https://supabase.com)

### Step 1: Set Up Supabase

1. Create a new Supabase project
2. The database schema is already created (tasks table with RLS)
3. Note your project URL and anon key from Settings > API

### Step 2: Deploy to Railway

#### Option A: Deploy via GitHub

1. Connect your GitHub repository to Railway
2. Railway will auto-detect the Python project
3. It will use `nixpacks.toml` for build configuration

#### Option B: Deploy via Railway CLI

```bash
# Install Railway CLI
npm i -g @railway/cli

# Login
railway login

# Initialize project
railway init

# Deploy
railway up
```

### Step 3: Add Redis Service

1. In Railway dashboard, click "New Service"
2. Select "Database" → "Redis"
3. Railway will automatically create a Redis instance
4. The `REDIS_URL` will be available as `${{Redis.REDIS_URL}}`

### Step 4: Configure Environment Variables

In Railway dashboard, add these environment variables:

```
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=your-anon-key-here
REDIS_URL=${{Redis.REDIS_URL}}
RAILWAY_PUBLIC_URL=${{RAILWAY_PUBLIC_DOMAIN}}
MAX_FILE_SIZE_MB=100
MAX_CONCURRENT_WORKERS=3
TASK_TTL_HOURS=2
VIDEO_OUTPUT_DIR=/app/videos
WHISPER_MODEL_CACHE_DIR=/app/whisper_cache
```

### Step 5: Deploy Worker Service

Railway's Procfile supports multiple processes. To run both web and worker:

1. In Railway dashboard, create a new service from the same repository
2. For the web service:
   - Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
3. For the worker service:
   - Command: `python worker.py`
   - This service doesn't need a PORT

### Step 6: Configure Health Checks

1. Go to service settings in Railway
2. Set health check path to `/health`
3. Set health check timeout to 300 seconds

### Step 7: Verify Deployment

```bash
# Check health
curl https://your-app.railway.app/health

# Test caption endpoint
curl -X POST "https://your-app.railway.app/tasks/caption" \
  -H "Content-Type: application/json" \
  -d '{"video_url": "https://example.com/video.mp4", "model_size": "small"}'
```

---

## Docker Deployment (Alternative)

If you prefer Docker:

### Dockerfile for Web Service

```dockerfile
FROM python:3.9-slim

# Install FFmpeg
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create directories
RUN mkdir -p videos whisper_cache

# Expose port
EXPOSE 8000

# Run application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Dockerfile for Worker Service

```dockerfile
FROM python:3.9-slim

# Install FFmpeg
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create directories
RUN mkdir -p videos whisper_cache

# Run worker
CMD ["python", "worker.py"]
```

### Docker Compose

```yaml
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  web:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    environment:
      - VITE_SUPABASE_URL=${VITE_SUPABASE_URL}
      - VITE_SUPABASE_ANON_KEY=${VITE_SUPABASE_ANON_KEY}
      - REDIS_URL=redis://redis:6379
      - RAILWAY_PUBLIC_URL=http://localhost:8000
      - MAX_FILE_SIZE_MB=100
      - MAX_CONCURRENT_WORKERS=3
    depends_on:
      - redis
    volumes:
      - ./videos:/app/videos
      - ./whisper_cache:/app/whisper_cache

  worker:
    build:
      context: .
      dockerfile: Dockerfile.worker
    environment:
      - VITE_SUPABASE_URL=${VITE_SUPABASE_URL}
      - VITE_SUPABASE_ANON_KEY=${VITE_SUPABASE_ANON_KEY}
      - REDIS_URL=redis://redis:6379
      - RAILWAY_PUBLIC_URL=http://localhost:8000
      - MAX_FILE_SIZE_MB=100
      - MAX_CONCURRENT_WORKERS=3
    depends_on:
      - redis
    volumes:
      - ./videos:/app/videos
      - ./whisper_cache:/app/whisper_cache

volumes:
  redis_data:
```

Run with:
```bash
docker-compose up -d
```

---

## Production Checklist

### Security
- [ ] Enable HTTPS (Railway provides this automatically)
- [ ] Rotate Supabase keys if exposed
- [ ] Set up rate limiting (consider Cloudflare)
- [ ] Review RLS policies in Supabase
- [ ] Add authentication for admin endpoints

### Performance
- [ ] Scale worker instances based on load
- [ ] Monitor Redis memory usage
- [ ] Set up CDN for video serving (Cloudflare R2, AWS S3)
- [ ] Configure proper video output storage (not ephemeral disk)
- [ ] Add caching layer for task status queries

### Monitoring
- [ ] Set up error tracking (Sentry, Rollbar)
- [ ] Configure log aggregation (Logtail, Papertrail)
- [ ] Add metrics collection (Prometheus, Grafana)
- [ ] Set up uptime monitoring (UptimeRobot, Pingdom)
- [ ] Create alerts for queue length and errors

### Maintenance
- [ ] Schedule database backups
- [ ] Document incident response procedures
- [ ] Set up CI/CD pipeline
- [ ] Create load testing scripts
- [ ] Document scaling procedures

### Storage
- [ ] Consider using S3-compatible storage for videos
- [ ] Implement video retention policies
- [ ] Add video compression options
- [ ] Set up backup storage location

---

## Scaling Guidelines

### Horizontal Scaling

**Web Service:**
- Can scale to multiple instances
- Load balanced automatically by Railway
- Each instance handles its own requests
- Shared Redis queue ensures no duplicate processing

**Worker Service:**
- Can scale to multiple instances
- Each worker polls the same Redis queue
- Redis BRPOP is atomic, preventing duplicate processing
- Recommended: 1 worker per 2GB RAM

### Vertical Scaling

**Memory Requirements:**
- Base: 512MB
- Per Whisper model: 1-4GB depending on size
- Per concurrent FFmpeg process: 200-500MB
- Recommended: 2GB minimum for production

**CPU Requirements:**
- FFmpeg and Whisper are CPU-intensive
- Recommended: 2+ vCPUs
- Scale workers based on queue length

### Queue Management

Monitor queue length:
```bash
curl https://your-app.railway.app/health
```

If queue length consistently > 10:
- Add more worker instances
- Increase MAX_CONCURRENT_WORKERS
- Consider dedicated worker machines

---

## Troubleshooting

### Worker not processing tasks

**Check Redis connection:**
```python
import redis
r = redis.from_url("your-redis-url")
print(r.ping())
```

**Check queue length:**
```bash
redis-cli -u your-redis-url
> LLEN ffmpeg:queue
```

### Videos not accessible

**Check file permissions:**
```bash
ls -la videos/
```

**Verify RAILWAY_PUBLIC_URL:**
```bash
echo $RAILWAY_PUBLIC_URL
```

### Out of disk space

**Check disk usage:**
```bash
df -h
```

**Manual cleanup:**
```bash
# Remove videos older than 2 hours
find videos/ -name "*.mp4" -mmin +120 -delete
```

### FFmpeg errors

**Check FFmpeg installation:**
```bash
ffmpeg -version
```

**Test FFmpeg:**
```bash
ffmpeg -i input.mp4 -c copy output.mp4
```

---

## Support

For issues or questions:
- Check logs in Railway dashboard
- Review error messages in Supabase
- Consult FFmpeg documentation
- Review Whisper model documentation
