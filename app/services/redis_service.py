import redis.asyncio as redis
import json
import logging
from typing import Optional, Dict, Any
from uuid import UUID
from app.config import settings

logger = logging.getLogger(__name__)


class RedisService:
    """Service for managing Redis task queue and metadata"""

    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.queue_key = "ffmpeg:queue"
        self.task_key_prefix = "ffmpeg:task:"

    async def connect(self) -> None:
        """Establish connection to Redis"""
        try:
            self.redis_client = await redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=10
            )
            await self.redis_client.ping()
            logger.info("Redis connection established")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    async def disconnect(self) -> None:
        """Close Redis connection"""
        if self.redis_client:
            await self.redis_client.close()
            logger.info("Redis connection closed")

    async def is_healthy(self) -> bool:
        """Check if Redis connection is healthy"""
        try:
            if not self.redis_client:
                return False
            await self.redis_client.ping()
            return True
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return False

    async def enqueue_task(self, task_id: UUID, task_type: str) -> bool:
        """
        Add a task to the processing queue

        Args:
            task_id: Unique task identifier
            task_type: Type of task (caption, merge, background_music)

        Returns:
            True if enqueued successfully
        """
        try:
            task_data = {
                "task_id": str(task_id),
                "task_type": task_type
            }

            logger.debug(f"Enqueuing task {task_id} to queue {self.queue_key}")
            await self.redis_client.lpush(self.queue_key, json.dumps(task_data))

            task_key = f"{self.task_key_prefix}{task_id}"
            await self.redis_client.setex(
                task_key,
                settings.task_ttl_seconds,
                json.dumps(task_data)
            )

            queue_length = await self.redis_client.llen(self.queue_key)
            logger.info(f"Task {task_id} enqueued with type {task_type}. Queue length: {queue_length}")
            return True
        except Exception as e:
            logger.error(f"Failed to enqueue task {task_id}: {e}", exc_info=True)
            return False

    async def dequeue_task(self, timeout: int = 5) -> Optional[Dict[str, Any]]:
        """
        Remove and return a task from the queue (blocking operation)

        Args:
            timeout: How long to wait for a task (seconds)

        Returns:
            Task data dictionary or None if timeout
        """
        try:
            logger.debug(f"Waiting for task from queue {self.queue_key} (timeout: {timeout}s)")
            result = await self.redis_client.brpop(self.queue_key, timeout=timeout)
            if result:
                _, task_json = result
                task_data = json.loads(task_json)
                logger.info(f"Dequeued task: {task_data['task_id']} of type {task_data.get('task_type')}")
                return task_data
            logger.debug("No task available in queue")
            return None
        except Exception as e:
            logger.error(f"Failed to dequeue task: {e}", exc_info=True)
            return None

    async def get_queue_length(self) -> int:
        """Get the number of tasks waiting in the queue"""
        try:
            length = await self.redis_client.llen(self.queue_key)
            return length
        except Exception as e:
            logger.error(f"Failed to get queue length: {e}")
            return 0

    async def update_task_metadata(self, task_id: UUID, metadata: Dict[str, Any]) -> bool:
        """
        Update task metadata in Redis

        Args:
            task_id: Task identifier
            metadata: Metadata to store

        Returns:
            True if updated successfully
        """
        try:
            task_key = f"{self.task_key_prefix}{task_id}"
            await self.redis_client.setex(
                task_key,
                settings.task_ttl_seconds,
                json.dumps(metadata)
            )
            return True
        except Exception as e:
            logger.error(f"Failed to update task metadata for {task_id}: {e}")
            return False

    async def get_task_metadata(self, task_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Retrieve task metadata from Redis

        Args:
            task_id: Task identifier

        Returns:
            Task metadata or None if not found
        """
        try:
            task_key = f"{self.task_key_prefix}{task_id}"
            data = await self.redis_client.get(task_key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.error(f"Failed to get task metadata for {task_id}: {e}")
            return None

    async def delete_task_metadata(self, task_id: UUID) -> bool:
        """
        Delete task metadata from Redis

        Args:
            task_id: Task identifier

        Returns:
            True if deleted successfully
        """
        try:
            task_key = f"{self.task_key_prefix}{task_id}"
            await self.redis_client.delete(task_key)
            return True
        except Exception as e:
            logger.error(f"Failed to delete task metadata for {task_id}: {e}")
            return False


redis_service = RedisService()
