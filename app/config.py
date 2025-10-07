import os
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application configuration settings loaded from environment variables"""

    # Supabase
    supabase_url: str = os.getenv("Database_URL", "").lstrip("=")
    supabase_key: str = os.getenv("Database_ANON_KEY", "").lstrip("=")

    # Redis
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379")

    # Server
    port: int = int(os.getenv("PORT", "8000"))
    railway_public_url: str = os.getenv("RAILWAY_PUBLIC_URL", "http://localhost:8000")

    # File handling
    max_file_size_mb: int = int(os.getenv("MAX_FILE_SIZE_MB", "100"))
    max_concurrent_workers: int = int(os.getenv("MAX_CONCURRENT_WORKERS", "3"))
    task_ttl_hours: int = int(os.getenv("TASK_TTL_HOURS", "2"))
    video_output_dir: str = os.getenv("VIDEO_OUTPUT_DIR", "/tmp/videos")
    whisper_model_cache_dir: str = os.getenv("WHISPER_MODEL_CACHE_DIR", "/tmp/whisper_cache")

    # Computed properties
    @property
    def max_file_size_bytes(self) -> int:
        """Convert max file size from MB to bytes"""
        return self.max_file_size_mb * 1024 * 1024

    @property
    def task_ttl_seconds(self) -> int:
        """Convert task TTL from hours to seconds"""
        return self.task_ttl_hours * 3600

    def validate_config(self) -> None:
        """Validate that all required configuration is present"""
        if not self.supabase_url:
            raise ValueError("Database_URL environment variable is required")
        if not self.supabase_key:
            raise ValueError("Database_ANON_KEY environment variable is required")

        try:
            os.makedirs(self.video_output_dir, exist_ok=True)
            os.makedirs(self.whisper_model_cache_dir, exist_ok=True)
        except Exception as e:
            import logging
            logging.warning(f"Could not create directories: {e}")

    class Config:
        env_file = ".env"


settings = Settings()
