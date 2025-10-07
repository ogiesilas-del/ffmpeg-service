from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
import logging
from utils.file_utils import get_video_path

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/video", tags=["videos"])


@router.get("/{filename}")
async def serve_video(filename: str):
    """
    Serve a processed video file

    Returns the processed video file for streaming/download.
    Only serves files matching the pattern: {task_id}_(captioned|merged|with_music).mp4

    - **filename**: Name of the video file to serve
    """
    try:
        video_path = get_video_path(filename)

        if not video_path:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Video not found"
            )

        return FileResponse(
            path=video_path,
            media_type="video/mp4",
            filename=filename,
            headers={
                "Content-Disposition": f'inline; filename="{filename}"',
                "Cache-Control": "public, max-age=3600",
                "Accept-Ranges": "bytes"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving video {filename}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )
