# API Usage Examples

## Caption Task Example

### Submit Caption Task

```bash
curl -X POST "http://localhost:8000/tasks/caption" \
  -H "Content-Type: application/json" \
  -d '{
    "video_url": "https://assets.json2video.com/clients/ie2ZO4Au3E/renders/2025-10-06-04355.mp4",
    "model_size": "small"
  }'
```

**Response:**
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "queued",
  "message": "Caption task queued successfully"
}
```

### Check Task Status

```bash
curl "http://localhost:8000/tasks/550e8400-e29b-41d4-a716-446655440000"
```

**Response (Processing):**
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "running",
  "video_url": null,
  "error": null,
  "created_at": "2025-10-07T12:00:00Z",
  "updated_at": "2025-10-07T12:01:00Z",
  "completed_at": null
}
```

**Response (Complete):**
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "success",
  "video_url": "https://your-app.railway.app/video/550e8400-e29b-41d4-a716-446655440000_captioned.mp4",
  "error": null,
  "created_at": "2025-10-07T12:00:00Z",
  "updated_at": "2025-10-07T12:05:00Z",
  "completed_at": "2025-10-07T12:05:00Z"
}
```

### Download Processed Video

```bash
curl "http://localhost:8000/video/550e8400-e29b-41d4-a716-446655440000_captioned.mp4" \
  -o captioned_video.mp4
```

---

## Merge Task Example

### Submit Merge Task

```bash
curl -X POST "http://localhost:8000/tasks/merge" \
  -H "Content-Type: application/json" \
  -d '{
    "scene_clip_urls": [
      "https://dashscope-result-sh.oss-cn-shanghai.aliyuncs.com/1d/ec/20251006/621d405c/d4ca0899-3ae0-4e39-a1ad-72c566cb523e.mp4",
      "https://dashscope-result-sh.oss-cn-shanghai.aliyuncs.com/1d/95/20251006/bd55ff35/f8136329-edf4-42ef-b2f9-41e6c150bc89.mp4"
    ],
    "voiceover_urls": [
      "https://v3.fal.media/files/koala/R9xah-zpIWdujeJVfI_Lh_output.mp3",
      "https://v3.fal.media/files/rabbit/0UNjgXiomqsqpRwtebRTj_output.mp3"
    ],
    "width": 1080,
    "height": 1920,
    "video_volume": 0.2,
    "voiceover_volume": 2.0
  }'
```

**Response:**
```json
{
  "task_id": "660f9511-f39c-52e5-b827-557766551111",
  "status": "queued",
  "message": "Merge task queued successfully"
}
```

### Poll for Completion

```bash
# Poll every 5 seconds until complete
while true; do
  curl -s "http://localhost:8000/tasks/660f9511-f39c-52e5-b827-557766551111" | jq .
  sleep 5
done
```

---

## Background Music Task Example

### Submit Background Music Task

```bash
curl -X POST "http://localhost:8000/tasks/background-music" \
  -H "Content-Type: application/json" \
  -d '{
    "video_url": "https://assets.json2video.com/clients/ie2ZO4Au3E/renders/2025-10-06-26438.mp4",
    "music_url": "https://v3.fal.media/files/zebra/m8xVxf5xojnXa8SB5oUnd_normalized_audio.wav",
    "music_volume": 0.3,
    "video_volume": 1.0
  }'
```

**Response:**
```json
{
  "task_id": "770fa622-g4ad-63f6-c938-668877662222",
  "status": "queued",
  "message": "Background music task queued successfully"
}
```

---

## Python Client Example

```python
import requests
import time

BASE_URL = "http://localhost:8000"

def submit_caption_task(video_url: str, model_size: str = "small"):
    """Submit a caption task"""
    response = requests.post(
        f"{BASE_URL}/tasks/caption",
        json={
            "video_url": video_url,
            "model_size": model_size
        }
    )
    response.raise_for_status()
    return response.json()

def get_task_status(task_id: str):
    """Get task status"""
    response = requests.get(f"{BASE_URL}/tasks/{task_id}")
    response.raise_for_status()
    return response.json()

def wait_for_completion(task_id: str, poll_interval: int = 5):
    """Poll task until completion"""
    while True:
        status_data = get_task_status(task_id)
        status = status_data["status"]

        print(f"Status: {status}")

        if status == "success":
            return status_data["video_url"]
        elif status == "failed":
            raise Exception(f"Task failed: {status_data.get('error')}")

        time.sleep(poll_interval)

def download_video(video_url: str, output_path: str):
    """Download processed video"""
    response = requests.get(video_url, stream=True)
    response.raise_for_status()

    with open(output_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

    print(f"Video downloaded: {output_path}")

# Example usage
if __name__ == "__main__":
    # Submit task
    task = submit_caption_task(
        "https://assets.json2video.com/clients/ie2ZO4Au3E/renders/2025-10-06-04355.mp4"
    )
    task_id = task["task_id"]
    print(f"Task submitted: {task_id}")

    # Wait for completion
    video_url = wait_for_completion(task_id)
    print(f"Video ready: {video_url}")

    # Download
    download_video(video_url, "output_captioned.mp4")
```

---

## JavaScript/Node.js Client Example

```javascript
const axios = require('axios');

const BASE_URL = 'http://localhost:8000';

async function submitCaptionTask(videoUrl, modelSize = 'small') {
  const response = await axios.post(`${BASE_URL}/tasks/caption`, {
    video_url: videoUrl,
    model_size: modelSize
  });
  return response.data;
}

async function getTaskStatus(taskId) {
  const response = await axios.get(`${BASE_URL}/tasks/${taskId}`);
  return response.data;
}

async function waitForCompletion(taskId, pollInterval = 5000) {
  while (true) {
    const statusData = await getTaskStatus(taskId);
    const status = statusData.status;

    console.log(`Status: ${status}`);

    if (status === 'success') {
      return statusData.video_url;
    } else if (status === 'failed') {
      throw new Error(`Task failed: ${statusData.error}`);
    }

    await new Promise(resolve => setTimeout(resolve, pollInterval));
  }
}

// Example usage
(async () => {
  try {
    // Submit task
    const task = await submitCaptionTask(
      'https://assets.json2video.com/clients/ie2ZO4Au3E/renders/2025-10-06-04355.mp4'
    );
    console.log(`Task submitted: ${task.task_id}`);

    // Wait for completion
    const videoUrl = await waitForCompletion(task.task_id);
    console.log(`Video ready: ${videoUrl}`);
  } catch (error) {
    console.error('Error:', error.message);
  }
})();
```

---

## Health Check Example

```bash
curl "http://localhost:8000/health"
```

**Response:**
```json
{
  "status": "healthy",
  "redis": "connected",
  "supabase": "connected",
  "queue_length": 3
}
```

---

## Error Handling Examples

### File Too Large

```bash
curl -X POST "http://localhost:8000/tasks/caption" \
  -H "Content-Type: application/json" \
  -d '{
    "video_url": "https://example.com/huge-video.mp4",
    "model_size": "small"
  }'
```

**Response (413):**
```json
{
  "detail": "File size 150.5MB exceeds limit of 100MB"
}
```

### Invalid URL

```bash
curl -X POST "http://localhost:8000/tasks/caption" \
  -H "Content-Type: application/json" \
  -d '{
    "video_url": "https://example.com/nonexistent.mp4",
    "model_size": "small"
  }'
```

**Response (400):**
```json
{
  "detail": "Unable to access video URL: HTTP error 404"
}
```

### Task Not Found

```bash
curl "http://localhost:8000/tasks/00000000-0000-0000-0000-000000000000"
```

**Response (404):**
```json
{
  "detail": "Task not found"
}
```

---

## Advanced: Batch Processing

```python
import asyncio
import aiohttp

async def process_batch(video_urls, base_url="http://localhost:8000"):
    """Process multiple videos concurrently"""
    async with aiohttp.ClientSession() as session:
        # Submit all tasks
        tasks = []
        for url in video_urls:
            async with session.post(
                f"{base_url}/tasks/caption",
                json={"video_url": url, "model_size": "small"}
            ) as response:
                data = await response.json()
                tasks.append(data["task_id"])

        print(f"Submitted {len(tasks)} tasks")

        # Poll all tasks
        completed = []
        while len(completed) < len(tasks):
            for task_id in tasks:
                if task_id in completed:
                    continue

                async with session.get(f"{base_url}/tasks/{task_id}") as response:
                    data = await response.json()

                    if data["status"] == "success":
                        completed.append(task_id)
                        print(f"Completed: {task_id} -> {data['video_url']}")
                    elif data["status"] == "failed":
                        completed.append(task_id)
                        print(f"Failed: {task_id} -> {data['error']}")

            await asyncio.sleep(5)

        print("All tasks completed")

# Run batch processing
video_urls = [
    "https://example.com/video1.mp4",
    "https://example.com/video2.mp4",
    "https://example.com/video3.mp4"
]

asyncio.run(process_batch(video_urls))
```
