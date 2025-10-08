import os
import tempfile
import logging
import whisper
import asyncio
from uuid import UUID
from typing import Dict, Any
from concurrent.futures import ThreadPoolExecutor
from app.models.task import TaskStatus
from app.services.supabase_service import supabase_service
from app.config import settings
from utils.file_utils import download_file, cleanup_temp_files, check_disk_space
from utils.ffmpeg_utils import (
    write_srt,
    burn_subtitles,
    merge_video_audio,
    concat_videos,
    add_background_music
)

logger = logging.getLogger(__name__)


async def process_caption_task(task_id: UUID, task_data: Dict[str, Any]) -> None:
    """
    Process a video captioning task

    Args:
        task_id: Task identifier
        task_data: Task data from Supabase
    """
    video_path = None
    output_path = None

    try:
        logger.info(f"[{task_id}] Starting caption task")
        logger.info(f"[{task_id}] Task data: {task_data}")

        logger.info(f"[{task_id}] Updating task status to RUNNING")
        supabase_service.update_task_status(task_id, TaskStatus.RUNNING)
        logger.info(f"[{task_id}] Status updated to RUNNING")

        video_url = task_data["video_url"]
        model_size = "small"

        video_filename = f"{task_id}_input.mp4"
        video_path = os.path.join(tempfile.gettempdir(), video_filename)

        if not check_disk_space(settings.max_file_size_bytes * 3):
            raise Exception("Insufficient disk space")

        logger.info(f"[{task_id}] Downloading video from {video_url}")
        _, file_size = await download_file(video_url, video_path)

        logger.info(f"[{task_id}] Transcribing audio with Whisper model: {model_size}")
        os.environ["WHISPER_CACHE_DIR"] = settings.whisper_model_cache_dir

        loop = asyncio.get_event_loop()
        logger.info(f"[{task_id}] Loading Whisper model...")
        with ThreadPoolExecutor() as executor:
            model = await loop.run_in_executor(executor, whisper.load_model, model_size)
            logger.info(f"[{task_id}] Model loaded, starting transcription...")
            result = await loop.run_in_executor(executor, model.transcribe, video_path)

        logger.info(f"[{task_id}] Transcription complete, found {len(result['segments'])} segments")
        subtitles = result["segments"]

        logger.info(f"[{task_id}] Generating SRT subtitles")
        srt_text = write_srt(subtitles, max_words_per_line=3)
        logger.info(f"[{task_id}] SRT generation complete")

        output_filename = f"{task_id}_captioned.mp4"
        output_path = os.path.join(settings.video_output_dir, output_filename)

        logger.info(f"[{task_id}] Burning subtitles into video using FFmpeg")
        with ThreadPoolExecutor() as executor:
            await loop.run_in_executor(executor, burn_subtitles, video_path, srt_text, output_path)
        logger.info(f"[{task_id}] Subtitle burning complete")

        result_url = f"{settings.railway_public_url}/video/{output_filename}"

        supabase_service.update_task_status(
            task_id,
            TaskStatus.SUCCESS,
            result_video_url=result_url,
            file_size=file_size
        )

        logger.info(f"[{task_id}] Caption task completed successfully")

    except Exception as e:
        error_msg = f"Caption task failed: {str(e)}"
        logger.error(f"[{task_id}] {error_msg}", exc_info=True)
        supabase_service.update_task_status(
            task_id,
            TaskStatus.FAILED,
            error_message=error_msg
        )
        if output_path and os.path.exists(output_path):
            os.remove(output_path)

    finally:
        cleanup_temp_files(video_path)


async def process_merge_task(task_id: UUID, task_data: Dict[str, Any]) -> None:
    """
    Process a video merging task

    Args:
        task_id: Task identifier
        task_data: Task data from Supabase
    """
    temp_files = []
    scene_files = []
    concat_list_path = None
    output_path = None

    try:
        logger.info(f"[{task_id}] Starting merge task")
        logger.info(f"[{task_id}] Task data: {task_data}")

        logger.info(f"[{task_id}] Updating task status to RUNNING")
        supabase_service.update_task_status(task_id, TaskStatus.RUNNING)
        logger.info(f"[{task_id}] Status updated to RUNNING")

        metadata = task_data.get("metadata", {})
        scene_urls = metadata["scene_clip_urls"]
        voiceover_urls = metadata["voiceover_urls"]
        width = metadata.get("width", 1080)
        height = metadata.get("height", 1920)
        video_volume = metadata.get("video_volume", 0.2)
        voiceover_volume = metadata.get("voiceover_volume", 2.0)

        if not check_disk_space(settings.max_file_size_bytes * len(scene_urls) * 5):
            raise Exception("Insufficient disk space")

        temp_dir = tempfile.mkdtemp(prefix=f"merge_{task_id}_")
        total_size = 0

        for i, (scene_url, voice_url) in enumerate(zip(scene_urls, voiceover_urls)):
            logger.info(f"[{task_id}] Processing scene {i+1}/{len(scene_urls)}")

            scene_path = os.path.join(temp_dir, f"scene_{i}_video.mp4")
            voice_path = os.path.join(temp_dir, f"scene_{i}_audio.mp3")

            _, size1 = await download_file(scene_url, scene_path)
            _, size2 = await download_file(voice_url, voice_path)
            total_size += size1 + size2

            temp_files.extend([scene_path, voice_path])

            scene_output = os.path.join(temp_dir, f"scene_{i}_final.mp4")

            logger.info(f"[{task_id}] Merging scene {i+1} video and audio with FFmpeg")
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor() as executor:
                await loop.run_in_executor(
                    executor,
                    merge_video_audio,
                    scene_path,
                    voice_path,
                    scene_output,
                    video_volume,
                    voiceover_volume,
                    5.0,
                    width,
                    height,
                    "cover"
                )
            logger.info(f"[{task_id}] Scene {i+1} merge complete")

            scene_files.append(scene_output)

        logger.info(f"[{task_id}] Concatenating {len(scene_files)} scenes")
        concat_list_path = os.path.join(temp_dir, "concat_list.txt")
        with open(concat_list_path, "w") as f:
            for scene_path in scene_files:
                escaped_path = scene_path.replace("\\", "/").replace("'", "'\\''")
                f.write(f"file '{escaped_path}'\n")

        output_filename = f"{task_id}_merged.mp4"
        output_path = os.path.join(settings.video_output_dir, output_filename)

        logger.info(f"[{task_id}] Concatenating all scenes with FFmpeg")
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as executor:
            await loop.run_in_executor(executor, concat_videos, concat_list_path, output_path)
        logger.info(f"[{task_id}] Concatenation complete")

        result_url = f"{settings.railway_public_url}/video/{output_filename}"

        supabase_service.update_task_status(
            task_id,
            TaskStatus.SUCCESS,
            result_video_url=result_url,
            file_size=total_size
        )

        logger.info(f"[{task_id}] Merge task completed successfully")

    except Exception as e:
        error_msg = f"Merge task failed: {str(e)}"
        logger.error(f"[{task_id}] {error_msg}", exc_info=True)
        supabase_service.update_task_status(
            task_id,
            TaskStatus.FAILED,
            error_message=error_msg
        )
        if output_path and os.path.exists(output_path):
            os.remove(output_path)

    finally:
        cleanup_temp_files(*temp_files, *scene_files, concat_list_path)
        if temp_dir and os.path.exists(temp_dir):
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)


async def process_background_music_task(task_id: UUID, task_data: Dict[str, Any]) -> None:
    """
    Process a background music task

    Args:
        task_id: Task identifier
        task_data: Task data from Supabase
    """
    video_path = None
    music_path = None
    output_path = None

    try:
        logger.info(f"[{task_id}] Starting background music task")
        logger.info(f"[{task_id}] Task data: {task_data}")

        logger.info(f"[{task_id}] Updating task status to RUNNING")
        supabase_service.update_task_status(task_id, TaskStatus.RUNNING)
        logger.info(f"[{task_id}] Status updated to RUNNING")

        video_url = task_data["video_url"]
        metadata = task_data.get("metadata", {})
        music_url = metadata["music_url"]
        music_volume = metadata.get("music_volume", 0.3)
        video_volume = metadata.get("video_volume", 1.0)

        if not check_disk_space(settings.max_file_size_bytes * 4):
            raise Exception("Insufficient disk space")

        temp_dir = tempfile.mkdtemp(prefix=f"music_{task_id}_")

        video_path = os.path.join(temp_dir, "input_video.mp4")
        music_path = os.path.join(temp_dir, "background_music.mp3")

        logger.info(f"[{task_id}] Downloading video and music")
        _, size1 = await download_file(video_url, video_path)
        _, size2 = await download_file(music_url, music_path)
        total_size = size1 + size2

        output_filename = f"{task_id}_with_music.mp4"
        output_path = os.path.join(settings.video_output_dir, output_filename)

        logger.info(f"[{task_id}] Adding background music to video with FFmpeg")
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as executor:
            await loop.run_in_executor(
                executor,
                add_background_music,
                video_path,
                music_path,
                output_path,
                music_volume,
                video_volume
            )
        logger.info(f"[{task_id}] Background music addition complete")

        result_url = f"{settings.railway_public_url}/video/{output_filename}"

        supabase_service.update_task_status(
            task_id,
            TaskStatus.SUCCESS,
            result_video_url=result_url,
            file_size=total_size
        )

        logger.info(f"[{task_id}] Background music task completed successfully")

    except Exception as e:
        error_msg = f"Background music task failed: {str(e)}"
        logger.error(f"[{task_id}] {error_msg}", exc_info=True)
        supabase_service.update_task_status(
            task_id,
            TaskStatus.FAILED,
            error_message=error_msg
        )
        if output_path and os.path.exists(output_path):
            os.remove(output_path)

    finally:
        cleanup_temp_files(video_path, music_path)
        if temp_dir and os.path.exists(temp_dir):
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
