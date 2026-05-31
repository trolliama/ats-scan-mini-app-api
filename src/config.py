import logging
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
LogEnv = Literal["dev", "prod"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
    )

    log_level: LogLevel = "INFO"
    log_env: LogEnv = "dev"
    log_color: bool = True

    @property
    def log_level_value(self) -> int:
        return getattr(logging, self.log_level, logging.INFO)

    @property
    def log_color_enabled(self) -> bool:
        """ANSI colors only in dev; disabled in prod regardless of LOG_COLOR."""
        return self.log_env == "dev" and self.log_color


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
