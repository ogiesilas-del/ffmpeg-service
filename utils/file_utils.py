import os
import httpx
import asyncio
import logging
from typing import Optional, Tuple, Dict
from pathlib import Path
from urllib.parse import urlparse, unquote, parse_qs
from datetime import datetime
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
        >>> extract_filename_from_url("https://dashscope-result-sh.oss-cn-shanghai.aliyuncs.com/1d/cd/20251008/bd55ff35/c758a8f7-e488-4be0-aa83-7dbbf7ef9c6f.mp4?Expires=1759943296&OSSAccessKeyId=LTAI5tKPD3TMqf2Lna1fASuh&Signature=8xfXrd5sNyx4uBPqduw1%2Bd9J7aQ%3D")
        'c758a8f7-e488-4be0-aa83-7dbbf7ef9c6f.mp4'
    """
    try:
        # Parse URL and extract path component only (without query parameters)
        parsed_url = urlparse(url)
        path = unquote(parsed_url.path)  # Decode URL-encoded characters
        filename = os.path.basename(path)

        # Handle empty or root path
        if not filename or filename == "/":
            logger.warning(f"Could not extract filename from URL: {url}")
            return default

        # Validate file extension
        valid_extensions = ['.mp4', '.mp3', '.wav', '.mov', '.avi', '.mkv', '.webm', '.m4a', '.aac', '.flac']
        if not any(filename.lower().endswith(ext) for ext in valid_extensions):
            logger.warning(f"Extracted filename has unexpected extension: {filename}")
            # Keep the filename but ensure it has an extension
            if '.' not in filename:
                filename = f"{filename}.mp4"

        # Remove invalid characters for Windows/Unix filesystems
        invalid_chars = '<>:"|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')

        # Remove leading/trailing spaces and dots
        filename = filename.strip('. ')

        # Ensure filename is not empty after cleaning
        if not filename:
            logger.warning(f"Filename became empty after cleaning: {url}")
            return default

        logger.info(f"Extracted filename from URL: {filename}")
        return filename

    except Exception as e:
        logger.error(f"Failed to extract filename from URL {url}: {e}")
        return default


async def check_file_size(url: str, headers: Optional[dict] = None) -> int:
    """
    Check the size of a remote file using HEAD request

    Args:
        url: URL of the file to check
        headers: Optional custom headers for the request

    Returns:
        File size in bytes (0 if Content-Length not available)

    Raises:
        FileSizeLimitExceeded: If file exceeds max size
        DownloadError: If unable to access URL
    """
    try:
        logger.info(f"Checking file size for: {url}")
        
        # Default headers to mimic browser request
        default_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "identity",  # Don't use gzip for cloud storage
            "Connection": "keep-alive",
            "Referer": url.split('?')[0]  # Use base URL as referer
        }
        
        if headers:
            default_headers.update(headers)
        
        # Configure httpx client with more lenient settings for cloud storage
        client_config = {
            "timeout": 30.0,
            "follow_redirects": True,
            "max_redirects": 10,
            "verify": True,  # Keep SSL verification
        }
        
        async with httpx.AsyncClient(**client_config) as client:
            try:
                response = await client.head(url, headers=default_headers)
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 405 or e.response.status_code == 403:
                    # HEAD not supported or forbidden, try GET with small range
                    logger.info("HEAD request failed, trying GET with range")
                    range_headers = default_headers.copy()
                    range_headers["Range"] = "bytes=0-1"
                    try:
                        response = await client.get(url, headers=range_headers)
                        response.raise_for_status()
                    except:
                        # If range request fails, skip size check
                        logger.warning("Could not check file size, skipping validation")
                        return 0
                else:
                    raise

            content_length = response.headers.get("content-length")
            if not content_length:
                content_range = response.headers.get("content-range")
                if content_range:
                    # Extract size from Content-Range: bytes 0-1/12345
                    try:
                        file_size = int(content_range.split('/')[-1])
                    except:
                        logger.warning(f"Could not parse Content-Range: {content_range}")
                        return 0
                else:
                    logger.warning(f"Content-Length header not found for {url}, will skip size check")
                    return 0
            else:
                file_size = int(content_length)

            # Check against configured max size
            if file_size > settings.max_file_size_bytes:
                raise FileSizeLimitExceeded(
                    f"File size {file_size / (1024*1024):.2f}MB exceeds limit of {settings.max_file_size_mb}MB"
                )

            logger.info(f"File size for {url}: {file_size / (1024*1024):.2f}MB")
            return file_size

    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code
        if status_code == 403:
            # Check if URL has expired
            is_expired, expiry_info = check_url_expiration(url)
            
            error_msg = (
                f"Access denied (403 Forbidden). "
            )
            
            if is_expired:
                error_msg += f"The URL has expired. {expiry_info}. Please generate a new pre-signed URL."
            else:
                # Don't fail on 403 during size check for cloud storage URLs
                logger.warning(f"403 on HEAD request, will attempt download anyway: {url}")
                return 0  # Skip size validation but allow download attempt
            
            # Only raise if definitely expired
            if is_expired:
                raise DownloadError(error_msg)
            return 0
            
        elif status_code == 404:
            raise DownloadError(f"File not found (404). Please verify the URL is correct.")
        else:
            # Don't fail on other errors during size check
            logger.warning(f"HTTP {status_code} during size check, will skip validation")
            return 0
            
    except httpx.RequestError as e:
        logger.warning(f"Network error during size check (will skip): {str(e)}")
        return 0
    except ValueError:
        logger.warning("Invalid Content-Length header, will skip size check")
        return 0


async def download_file(
    url: str, 
    output_path: str, 
    skip_size_check: bool = False,
    headers: Optional[dict] = None,
    max_retries: int = 3
) -> Tuple[str, int]:
    """
    Download a file from URL to local path with progress tracking and retry logic

    Args:
        url: URL of the file to download
        output_path: Local path to save the file
        skip_size_check: Skip initial file size check (useful for servers that don't support HEAD)
        headers: Optional custom headers for the request
        max_retries: Maximum number of retry attempts on failure

    Returns:
        Tuple of (output_path, file_size)

    Raises:
        FileSizeLimitExceeded: If file exceeds max size
        DownloadError: If download fails after all retries
    """
    # Default headers optimized for cloud storage (similar to requests library)
    default_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "identity",  # Don't compress for cloud storage
        "Connection": "keep-alive",
    }
    
    if headers:
        default_headers.update(headers)
    
    last_error = None
    
    for attempt in range(max_retries):
        try:
            # Check file size first (unless skipped)
            if not skip_size_check and attempt == 0:
                try:
                    file_size = await check_file_size(url, headers=default_headers)
                except DownloadError:
                    # If size check fails, log but continue with download
                    logger.warning("Size check failed, proceeding with download anyway")
                    file_size = 0
            else:
                file_size = 0

            logger.info(f"Downloading {url} to {output_path} (attempt {attempt + 1}/{max_retries})")

            # Ensure output directory exists
            output_dir = os.path.dirname(output_path)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)

            # Configure httpx client similar to requests
            client_config = {
                "timeout": httpx.Timeout(
                    connect=30.0,
                    read=300.0,
                    write=30.0,
                    pool=30.0
                ),
                "follow_redirects": True,
                "max_redirects": 10,
                "verify": True,
            }

            async with httpx.AsyncClient(**client_config) as client:
                async with client.stream("GET", url, headers=default_headers) as response:
                    response.raise_for_status()

                    downloaded_size = 0
                    chunk_count = 0
                    
                    with open(output_path, "wb") as f:
                        async for chunk in response.aiter_bytes(chunk_size=8192):
                            f.write(chunk)
                            downloaded_size += len(chunk)
                            chunk_count += 1
                            
                            # Log progress every 1000 chunks (~8MB)
                            if chunk_count % 1000 == 0:
                                logger.info(f"Downloaded {downloaded_size / (1024*1024):.2f}MB...")

                            # Check size during download
                            if downloaded_size > settings.max_file_size_bytes:
                                # Clean up partial file
                                try:
                                    os.remove(output_path)
                                except:
                                    pass
                                raise FileSizeLimitExceeded(
                                    f"Download exceeded size limit of {settings.max_file_size_mb}MB"
                                )

            actual_size = os.path.getsize(output_path)
            logger.info(f"Download complete: {output_path} ({actual_size / (1024*1024):.2f}MB)")

            return output_path, actual_size

        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            if status_code == 403:
                # Check if URL has expired
                is_expired, expiry_info = check_url_expiration(url)
                
                if is_expired:
                    error_msg = (
                        f"Access denied (403 Forbidden). "
                        f"The URL has expired. {expiry_info}. "
                        f"Please generate a new pre-signed URL."
                    )
                    raise DownloadError(error_msg)
                else:
                    # 403 but not expired - might be temporary, retry
                    last_error = DownloadError(f"Access denied (403), retrying...")
                    if attempt < max_retries - 1:
                        logger.warning(f"403 error, attempt {attempt + 1}/{max_retries}, retrying...")
                        await asyncio.sleep(2 ** attempt)
                        continue
                    else:
                        error_msg = (
                            f"Access denied (403 Forbidden). "
                            f"The URL may require special authentication or may be region-restricted. "
                            f"Please verify the URL is publicly accessible."
                        )
                        raise DownloadError(error_msg)
                        
            elif status_code == 404:
                raise DownloadError(f"File not found (404). Please verify the URL is correct.")
            elif status_code >= 500:
                # Server errors might be temporary, retry
                last_error = DownloadError(f"Server error {status_code}, retrying...")
                logger.warning(f"Server error {status_code}, attempt {attempt + 1}/{max_retries}")
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
                continue
            else:
                raise DownloadError(f"HTTP error {status_code} during download")
                
        except httpx.RequestError as e:
            last_error = DownloadError(f"Network error: {str(e)}")
            if attempt < max_retries - 1:
                logger.warning(f"Network error, retrying in {2 ** attempt} seconds...")
                await asyncio.sleep(2 ** attempt)
                continue
            else:
                raise last_error
                
        except FileSizeLimitExceeded:
            raise  # Don't retry size limit errors
            
        except Exception as e:
            # Clean up partial download
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except:
                    pass
            
            last_error = DownloadError(f"Download failed: {str(e)}")
            if attempt < max_retries - 1:
                logger.warning(f"Download failed, retrying in {2 ** attempt} seconds...")
                await asyncio.sleep(2 ** attempt)
                continue
            else:
                raise last_error
    
    # If we get here, all retries failed
    raise last_error or DownloadError("Download failed after all retries")


def validate_filename(filename: str) -> bool:
    """
    Validate filename to prevent directory traversal attacks

    Args:
        filename: Filename to validate

    Returns:
        True if filename is safe
    """
    # Prevent directory traversal
    if ".." in filename or "/" in filename or "\\" in filename:
        return False

    # Check for valid suffixes
    valid_suffixes = ["_captioned.mp4", "_merged.mp4", "_with_music.mp4", "_final.mp4", "_composed.mp4"]
    if not any(filename.endswith(suffix) for suffix in valid_suffixes):
        return False

    try:
        # Basic structure validation
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
        # Cross-platform disk space check
        if os.name == 'nt':  # Windows
            import ctypes
            free_bytes = ctypes.c_ulonglong(0)
            ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                ctypes.c_wchar_p(settings.video_output_dir),
                None, None,
                ctypes.pointer(free_bytes)
            )
            return free_bytes.value
        else:  # Unix-like systems
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
    # Add 100MB buffer for safety
    required_with_buffer = required_bytes + (100 * 1024 * 1024)

    if available < required_with_buffer:
        logger.error(
            f"Insufficient disk space: {available / (1024*1024):.2f}MB available, "
            f"{required_with_buffer / (1024*1024):.2f}MB required"
        )
        return False

    logger.info(f"Disk space check passed: {available / (1024*1024):.2f}MB available")
    return True


def check_url_expiration(url: str) -> Tuple[bool, Optional[str]]:
    """
    Check if a pre-signed URL has expired based on the Expires parameter
    
    Args:
        url: URL to check (should contain Expires query parameter)
        
    Returns:
        Tuple of (is_expired, expiration_info)
        
    Example:
        >>> check_url_expiration("https://example.com/file.mp4?Expires=1234567890")
        (True, "URL expired on 2009-02-13 23:31:30 UTC")
    """
    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        
        # Check for Expires parameter (Unix timestamp)
        if 'Expires' in params:
            expires_timestamp = int(params['Expires'][0])
            expires_datetime = datetime.fromtimestamp(expires_timestamp)
            current_timestamp = datetime.now().timestamp()
            
            is_expired = current_timestamp > expires_timestamp
            
            if is_expired:
                return True, f"URL expired on {expires_datetime.strftime('%Y-%m-%d %H:%M:%S')} UTC"
            else:
                time_left = expires_timestamp - current_timestamp
                hours_left = int(time_left / 3600)
                return False, f"URL valid for {hours_left} more hours"
        
        return False, "No expiration detected"
        
    except Exception as e:
        logger.warning(f"Could not check URL expiration: {e}")
        return False, None


def check_url_expiration(url: str) -> Tuple[bool, Optional[str]]:
    """
    Check if a pre-signed URL has expired based on the Expires parameter
    
    Args:
        url: URL to check (should contain Expires query parameter)
        
    Returns:
        Tuple of (is_expired, expiration_info)
        
    Example:
        >>> check_url_expiration("https://example.com/file.mp4?Expires=1234567890")
        (True, "URL expired on 2009-02-13 23:31:30 UTC")
    """
    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        
        # Check for Expires parameter (Unix timestamp)
        if 'Expires' in params:
            expires_timestamp = int(params['Expires'][0])
            expires_datetime = datetime.fromtimestamp(expires_timestamp)
            current_timestamp = datetime.now().timestamp()
            
            is_expired = current_timestamp > expires_timestamp
            
            if is_expired:
                return True, f"URL expired on {expires_datetime.strftime('%Y-%m-%d %H:%M:%S')} UTC"
            else:
                time_left = expires_timestamp - current_timestamp
                hours_left = int(time_left / 3600)
                return False, f"URL valid for {hours_left} more hours"
        
        return False, "No expiration detected"
        
    except Exception as e:
        logger.warning(f"Could not check URL expiration: {e}")
        return False, None
    """
    Sanitize a file path to prevent security issues
    
    Args:
        path: Path to sanitize
        
    Returns:
        Sanitized path
    """
    # Remove null bytes
    path = path.replace('\0', '')
    
    # Normalize path
    path = os.path.normpath(path)
    
    # Remove leading slashes and dots
    while path.startswith(('.', '/', '\\')):
        path = path[1:]
    
    return path


def get_safe_filename(url: str, prefix: str = "", suffix: str = "") -> str:
    """
    Generate a safe filename from a URL with optional prefix/suffix
    
    Args:
        url: URL to extract filename from
        prefix: Optional prefix to add
        suffix: Optional suffix to add (before extension)
        
    Returns:
        Safe filename
        
    Example:
        >>> get_safe_filename("https://example.com/video.mp4", suffix="_processed")
        'video_processed.mp4'
    """
    base_filename = extract_filename_from_url(url)
    
    if suffix:
        name, ext = os.path.splitext(base_filename)
        base_filename = f"{name}{suffix}{ext}"
    
    if prefix:
        base_filename = f"{prefix}{base_filename}"
    
    return base_filename
