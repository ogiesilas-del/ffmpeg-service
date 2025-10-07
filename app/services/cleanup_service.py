import os
import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.config import settings
from app.services.supabase_service import supabase_service
from app.services.redis_service import redis_service

logger = logging.getLogger(__name__)


class CleanupService:
    """Service for cleaning up expired videos and old task records"""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()

    async def cleanup_old_videos(self) -> None:
        """
        Clean up videos and task records older than TTL threshold
        """
        try:
            logger.info("Starting cleanup of old videos...")

            old_tasks = supabase_service.get_old_tasks(hours=settings.task_ttl_hours)

            deleted_count = 0
            freed_space = 0

            for task in old_tasks:
                try:
                    task_id = task["id"]
                    result_url = task.get("result_video_url")

                    if result_url:
                        filename = result_url.split("/")[-1]
                        video_path = os.path.join(settings.video_output_dir, filename)

                        if os.path.exists(video_path):
                            file_size = os.path.getsize(video_path)
                            os.remove(video_path)
                            freed_space += file_size
                            deleted_count += 1
                            logger.info(f"Deleted video: {filename}")

                    await redis_service.delete_task_metadata(task_id)

                except Exception as e:
                    logger.error(f"Failed to cleanup task {task.get('id')}: {e}")

            logger.info(
                f"Cleanup complete: {deleted_count} videos deleted, "
                f"{freed_space / (1024*1024):.2f}MB freed"
            )

        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

    async def cleanup_orphaned_files(self) -> None:
        """
        Clean up video files that don't have corresponding database records
        """
        try:
            logger.info("Starting cleanup of orphaned files...")

            if not os.path.exists(settings.video_output_dir):
                return

            deleted_count = 0
            freed_space = 0

            for filename in os.listdir(settings.video_output_dir):
                if not filename.endswith(".mp4"):
                    continue

                file_path = os.path.join(settings.video_output_dir, filename)

                try:
                    task_id = filename.split("_")[0]

                    task_data = supabase_service.get_task(task_id)

                    if not task_data:
                        file_size = os.path.getsize(file_path)
                        os.remove(file_path)
                        freed_space += file_size
                        deleted_count += 1
                        logger.info(f"Deleted orphaned file: {filename}")

                except Exception as e:
                    logger.warning(f"Could not process file {filename}: {e}")

            logger.info(
                f"Orphaned file cleanup complete: {deleted_count} files deleted, "
                f"{freed_space / (1024*1024):.2f}MB freed"
            )

        except Exception as e:
            logger.error(f"Error during orphaned file cleanup: {e}")

    async def cleanup_temp_files(self) -> None:
        """
        Clean up temporary files from temp directory
        """
        try:
            import tempfile
            import shutil

            temp_dir = tempfile.gettempdir()
            deleted_count = 0

            for item in os.listdir(temp_dir):
                if item.startswith(("merge_", "music_", "ffmpeg_compose_")):
                    item_path = os.path.join(temp_dir, item)

                    try:
                        if os.path.isdir(item_path):
                            mtime = os.path.getmtime(item_path)
                            age_hours = (datetime.now().timestamp() - mtime) / 3600

                            if age_hours > 3:
                                shutil.rmtree(item_path)
                                deleted_count += 1
                                logger.info(f"Deleted old temp directory: {item}")

                    except Exception as e:
                        logger.warning(f"Could not cleanup temp item {item}: {e}")

            if deleted_count > 0:
                logger.info(f"Temp file cleanup: {deleted_count} directories removed")

        except Exception as e:
            logger.error(f"Error during temp file cleanup: {e}")

    async def run_all_cleanup(self) -> None:
        """Run all cleanup tasks"""
        await self.cleanup_old_videos()
        await self.cleanup_orphaned_files()
        await self.cleanup_temp_files()

    def start(self) -> None:
        """Start the cleanup scheduler"""
        logger.info("Starting cleanup scheduler (runs every hour)...")

        self.scheduler.add_job(
            self.run_all_cleanup,
            'interval',
            hours=1,
            id='cleanup_task',
            replace_existing=True
        )

        self.scheduler.start()
        logger.info("Cleanup scheduler started")

    def stop(self) -> None:
        """Stop the cleanup scheduler"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Cleanup scheduler stopped")


cleanup_service = CleanupService()
