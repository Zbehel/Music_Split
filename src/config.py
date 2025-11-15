from pydantic_settings import BaseSettings
from pydantic import ConfigDict
from typing import Literal


class Settings(BaseSettings):
    # Model configuration
    model_name: str = "htdemucs"  # Default to 4-stem model
    device: str = "auto"

    # API configuration
    results_dir: str = "results"
    max_file_size_mb: int = 100
    max_duration_seconds: int = 600  # 10 minutes max

    # Processing configuration
    cleanup_after_hours: int = 24  # Cleanup old results after 24h
    output_format: Literal["wav", "mp3", "flac"] = "wav"

    # Server configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        protected_namespaces=(
            "settings_",
        ),  # Only protect settings_ namespace, not model_
    )


settings = Settings()
