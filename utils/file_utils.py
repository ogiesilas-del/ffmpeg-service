import os
import httpx
import logging
from typing import Optional, Tuple
from pathlib import Path
from urllib.parse import urlparse, unquote
from app.config import settings

logger = logging.getLogger(__name__)


class FileSizeLimitExceeded(Exception):
    """Raised when file size exceeds the configured limit"""
    pass


class DownloadError(Exception):
    """Raised when file download fails"""
    pass


def extract_filename_from_url(url: str, default: str = "video.mp4") -> str:
    """
    Safely extract filename from URL, removing query parameters and handling edge cases

    Args:
        url: URL to extract filename from
        default: Default filename if extraction fails

    Returns:
        Clean filename without query parameters

    Example:
        >>> extract_filename_from_url("https://example.com/video.mp4?token=123")
        'video.mp4'
        >>> extract_filename_from_url("https://example.com/path/to/my%20video.mp4")
        'my video.mp4'
    """
    try:
        parsed_url = urlparse(url)
        path = unquote(parsed_url.path)
        filename = os.path.basename(path)

        if not filename or filename == "/":
            logger.warning(f"Could not extract filename from URL: {url}")
            return default

        if not any(filename.lower().endswith(ext) for ext in ['.mp4', '.mp3', '.wav', '.mov', '.avi', '.mkv', '.webm']):
            logger.warning(f"Extracted filename has unexpected extension: {filename}")
            filename = f"{filename}.mp4"

        invalid_chars = '<>:"|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')

        return filename
    except Exception as e:
        logger.error(f"Failed to extract filename from URL {url}: {e}")
        return default


async def check_file_size(url: str) -> int:
    """
    Check the size of a remote file using HEAD request

    Args:
        url: URL of the file to check

    Returns:
        File size in bytes

    Raises:
        FileSizeLimitExceeded: If file exceeds max size
        DownloadError: If unable to determine file size
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.head(url, follow_redirects=True)
            response.raise_for_status()

            content_length = response.headers.get("content-length")
            if not content_length:
                logger.warning(f"Content-Length header not found for {url}")
                return 0

            file_size = int(content_length)

            if file_size > settings.max_file_size_bytes:
                raise FileSizeLimitExceeded(
                    f"File size {file_size / (1024*1024):.2f}MB exceeds limit of {settings.max_file_size_mb}MB"
                )

            logger.info(f"File size for {url}: {file_size / (1024*1024):.2f}MB")
            return file_size

    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code
        if status_code == 403:
            raise DownloadError(
                f"Access denied (403 Forbidden). The URL may have expired or requires authentication. "
                f"Please ensure the URL is publicly accessible and not expired."
            )
        elif status_code == 404:
            raise DownloadError(f"File not found (404). Please verify the URL is correct.")
        else:
            raise DownloadError(f"HTTP error {status_code} while accessing URL")
    except httpx.RequestError as e:
        raise DownloadError(f"Network error checking file size: {str(e)}")
    except ValueError:
        raise DownloadError("Invalid Content-Length header")


async def download_file(url: str, output_path: str) -> Tuple[str, int]:
    """
    Download a file from URL to local path with progress tracking

    Args:
        url: URL of the file to download
        output_path: Local path to save the file

    Returns:
        Tuple of (output_path, file_size)

    Raises:
        FileSizeLimitExceeded: If file exceeds max size
        DownloadError: If download fails
    """
    try:
        file_size = await check_file_size(url)

        logger.info(f"Downloading {url} to {output_path}")

        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream("GET", url, follow_redirects=True) as response:
                response.raise_for_status()

                downloaded_size = 0
                with open(output_path, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        f.write(chunk)
                        downloaded_size += len(chunk)

                        if downloaded_size > settings.max_file_size_bytes:
                            os.remove(output_path)
                            raise FileSizeLimitExceeded(
                                f"Download exceeded size limit of {settings.max_file_size_mb}MB"
                            )

        actual_size = os.path.getsize(output_path)
        logger.info(f"Download complete: {output_path} ({actual_size / (1024*1024):.2f}MB)")

        return output_path, actual_size

    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code
        if status_code == 403:
            raise DownloadError(
                f"Access denied (403 Forbidden). The URL may have expired or requires authentication. "
                f"Please ensure the URL is publicly accessible and not expired."
            )
        elif status_code == 404:
            raise DownloadError(f"File not found (404). Please verify the URL is correct.")
        else:
            raise DownloadError(f"HTTP error {status_code} during download")
    except httpx.RequestError as e:
        raise DownloadError(f"Network error during download: {str(e)}")
    except Exception as e:
        if os.path.exists(output_path):
            os.remove(output_path)
        raise DownloadError(f"Download failed: {str(e)}")


def validate_filename(filename: str) -> bool:
    """
    Validate filename to prevent directory traversal attacks

    Args:
        filename: Filename to validate

    Returns:
        True if filename is safe
    """
    if ".." in filename or "/" in filename or "\\" in filename:
        return False

    if not filename.endswith(("_captioned.mp4", "_merged.mp4", "_with_music.mp4")):
        return False

    try:
        parts = filename.rsplit("_", 1)
        if len(parts) != 2:
            return False

        return True
    except Exception:
        return False


def get_video_path(filename: str) -> Optional[str]:
    """
    Get the full path to a video file if it exists

    Args:
        filename: Name of the video file

    Returns:
        Full path if file exists and is valid, None otherwise
    """
    if not validate_filename(filename):
        logger.warning(f"Invalid filename: {filename}")
        return None

    file_path = os.path.join(settings.video_output_dir, filename)

    if not os.path.exists(file_path):
        logger.warning(f"File not found: {file_path}")
        return None

    if not os.path.isfile(file_path):
        logger.warning(f"Not a file: {file_path}")
        return None

    return file_path


def cleanup_temp_files(*file_paths: str) -> None:
    """
    Clean up temporary files

    Args:
        *file_paths: Variable number of file paths to delete
    """
    for file_path in file_paths:
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"Cleaned up temp file: {file_path}")
        except Exception as e:
            logger.warning(f"Failed to cleanup {file_path}: {e}")


def get_disk_space_available() -> int:
    """
    Get available disk space in bytes

    Returns:
        Available disk space in bytes
    """
    try:
        stat = os.statvfs(settings.video_output_dir)
        return stat.f_bavail * stat.f_frsize
    except Exception as e:
        logger.error(f"Failed to get disk space: {e}")
        return 0


def check_disk_space(required_bytes: int) -> bool:
    """
    Check if enough disk space is available

    Args:
        required_bytes: Required space in bytes

    Returns:
        True if enough space is available
    """
    available = get_disk_space_available()
    # Add 100MB buffer
    required_with_buffer = required_bytes + (100 * 1024 * 1024)

    if available < required_with_buffer:
        logger.error(
            f"Insufficient disk space: {available / (1024*1024):.2f}MB available, "
            f"{required_with_buffer / (1024*1024):.2f}MB required"
        )
        return False

    return True
