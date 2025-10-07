import asyncio
import signal
import sys
import logging
from uuid import UUID
from app.config import settings
from app.services.redis_service import redis_service
from app.services.supabase_service import supabase_service
from app.models.task import TaskType
from workers.processors import (
    process_caption_task,
    process_merge_task,
    process_background_music_task
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

shutdown_event = asyncio.Event()
semaphore = None


def signal_handler(sig, frame):
    """Handle shutdown signals gracefully"""
    logger.info(f"Received signal {sig}, initiating graceful shutdown...")
    shutdown_event.set()


async def process_task(task_data: dict) -> None:
    """
    Process a single task based on its type

    Args:
        task_data: Task data from Redis queue
    """
    task_id = UUID(task_data["task_id"])
    task_type = task_data["task_type"]

    try:
        logger.info(f"="*60)
        logger.info(f"Starting to process task {task_id} of type {task_type}")
        logger.info(f"="*60)

        logger.info(f"Fetching full task data from Supabase for task {task_id}")
        full_task_data = supabase_service.get_task(task_id)

        if not full_task_data:
            logger.error(f"Task {task_id} not found in database - cannot process")
            return

        logger.info(f"Task {task_id} data retrieved: {full_task_data}")

        async with semaphore:
            if task_type == TaskType.CAPTION.value:
                logger.info(f"Routing task {task_id} to caption processor")
                await process_caption_task(task_id, full_task_data)
            elif task_type == TaskType.MERGE.value:
                logger.info(f"Routing task {task_id} to merge processor")
                await process_merge_task(task_id, full_task_data)
            elif task_type == TaskType.BACKGROUND_MUSIC.value:
                logger.info(f"Routing task {task_id} to background music processor")
                await process_background_music_task(task_id, full_task_data)
            else:
                logger.error(f"Unknown task type: {task_type}")

        logger.info(f"Task {task_id} processing completed")

    except Exception as e:
        logger.error(f"Error processing task {task_id}: {e}", exc_info=True)


async def worker_loop():
    """
    Main worker loop that polls Redis queue and processes tasks
    """
    global semaphore

    logger.info("="*60)
    logger.info("Starting video processing worker...")
    logger.info(f"Max concurrent workers: {settings.max_concurrent_workers}")
    logger.info(f"Redis URL: {settings.redis_url}")
    logger.info(f"Supabase URL: {settings.supabase_url}")
    logger.info("="*60)

    try:
        logger.info("Validating configuration...")
        settings.validate_config()
        logger.info("Configuration validated")

        logger.info("Connecting to Supabase...")
        supabase_service.connect()
        logger.info("Supabase connected")

        logger.info("Connecting to Redis...")
        await redis_service.connect()
        logger.info("Redis connected")

        semaphore = asyncio.Semaphore(settings.max_concurrent_workers)

        logger.info("Worker connections established successfully")
        logger.info("Starting main processing loop...")

        loop_count = 0
        while not shutdown_event.is_set():
            try:
                loop_count += 1
                if loop_count % 20 == 0:
                    queue_length = await redis_service.get_queue_length()
                    logger.info(f"Worker heartbeat - Queue length: {queue_length}")

                task_data = await redis_service.dequeue_task(timeout=5)

                if task_data:
                    logger.info(f"Task received from queue: {task_data}")
                    asyncio.create_task(process_task(task_data))
                else:
                    await asyncio.sleep(0.1)

            except Exception as e:
                logger.error(f"Error in worker loop: {e}", exc_info=True)
                await asyncio.sleep(5)

    except Exception as e:
        logger.error(f"Fatal error in worker: {e}", exc_info=True)
    finally:
        logger.info("Shutting down worker...")
        await redis_service.disconnect()
        logger.info("Worker shutdown complete")


def main():
    """Main entry point for the worker process"""
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        asyncio.run(worker_loop())
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
    except Exception as e:
        logger.error(f"Worker crashed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
