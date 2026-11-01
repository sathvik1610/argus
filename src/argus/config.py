"""Settings, read from environment variables or a local .env file."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDER_KEY = "your-gemini-api-key-here"


class ConfigError(Exception):
    """Raised when something required (like the API key) is not configured."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ARGUS_",
        env_file=".env",
        extra="ignore",
        # GOOGLE_API_KEY uses Google's standard name (no ARGUS_ prefix) via an
        # alias; populate_by_name also lets code/tests pass google_api_key=...
        populate_by_name=True,
    )

    google_api_key: str | None = Field(default=None, alias="GOOGLE_API_KEY")
    llm_model: str = "gemini-2.5-flash"
    embedding_model: str = "models/gemini-embedding-001"

    chroma_dir: Path = Path(".argus/chroma")
    top_k: int = 4  # how many retrieved snippets each review gets (3-5 works well)
    max_diff_chars: int = 12_000  # the diff is truncated past this size
    max_chunks_to_index: int = 1500  # safety cap on embedding calls per repo

    # Folders the API may read repos from, separated by os.pathsep (';' on Windows).
    allowed_repo_dirs: str = ""

    def allowed_dirs(self) -> list[Path]:
        parts = [p.strip() for p in self.allowed_repo_dirs.split(os.pathsep) if p.strip()]
        return [Path(p).resolve() for p in parts]

    def require_api_key(self) -> str:
        key = self.google_api_key
        if not key or key == PLACEHOLDER_KEY:
            raise ConfigError(
                "GOOGLE_API_KEY is not set. Copy .env.example to .env and add your key."
            )
        return key
