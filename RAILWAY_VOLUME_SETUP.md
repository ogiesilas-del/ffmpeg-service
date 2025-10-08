# Railway Persistent Volume Setup for Whisper Model Cache

To enable persistent storage for the Whisper AI model and dramatically speed up caption processing, follow these steps:

## Setup Instructions

### 1. Create a Persistent Volume in Railway

1. Go to your Railway project dashboard
2. Click on your service
3. Navigate to the **"Variables"** tab
4. Scroll down to **"Volume"** section
5. Click **"+ New Volume"**
6. Configure the volume:
   - **Mount Path**: `/data`
   - **Size**: At least 2GB (Whisper base model is ~150MB, but allow room for growth)
7. Click **"Add"**

### 2. Deploy the Updated Configuration

The code has been updated to:
- Store Whisper models in `/data/whisper-models` (persistent storage)
- Pre-download the model during build time to the persistent volume
- Cache the model in memory between requests

### 3. Verify the Setup

After deploying, check your logs to see:
- Build logs should show: `✅ Whisper model cached to /data/whisper-models`
- First caption task will use the cached model (should be very fast)
- Subsequent tasks will reuse the in-memory cached model (even faster)

## Performance Improvements

**Before (without persistent cache):**
- Model download + load time: ~30-60 seconds per deployment
- Transcription time: 5+ minutes for 30-second video

**After (with persistent cache):**
- Model load time: ~2-3 seconds (reading from disk)
- Transcription time: Same processing time, but no download overhead
- In-memory cache: Instant model access for subsequent requests

## Environment Variables (Optional Override)

If you need to customize the cache directory:

```
WHISPER_MODEL_CACHE_DIR=/data/whisper-models
```

## Troubleshooting

**If models aren't persisting:**
1. Verify the volume is mounted at `/data`
2. Check build logs for any permission errors
3. Ensure the volume has sufficient space

**If transcription is still slow:**
1. The actual transcription takes time based on video length
2. For 30-second videos, expect ~30-120 seconds of processing
3. Consider using a smaller model like "tiny" or "small" if accuracy allows

**To change the Whisper model:**
Edit `workers/processors.py` line 65 to use a different model:
- `tiny` - Fastest, less accurate
- `base` - Good balance (current default)
- `small` - More accurate, slower
- `medium` - Very accurate, much slower
- `large` - Best accuracy, very slow
