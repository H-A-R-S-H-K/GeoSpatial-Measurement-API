"""Runtime settings.

Environment variables use the ``GEO_`` prefix, for example
``GEO_MAX_UPLOAD_BYTES``.
"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Local configuration. Defaults are enough to run the service."""

    model_config = SettingsConfigDict(
        env_prefix="GEO_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str | None = None
    max_upload_bytes: int = Field(default=20 * 1024 * 1024, gt=0)
    max_zip_uncompressed_bytes: int = Field(default=100 * 1024 * 1024, gt=0)
    max_zip_entries: int = Field(default=64, gt=0)
    temp_dir: str | None = None

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        database_path = (PROJECT_ROOT / "data" / "geospatial.db").resolve()
        return f"sqlite:///{database_path}"

    @property
    def resolved_temp_dir(self) -> Path:
        if self.temp_dir:
            return Path(self.temp_dir)
        return PROJECT_ROOT / "data" / "tmp"


def get_settings() -> Settings:
    return Settings()
