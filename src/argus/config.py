"""Application configuration.

All runtime configuration is sourced from environment variables (optionally via a
``.env`` file) so the same codebase runs unmodified across local dev, CI, and
containers. See ``.env.example`` for the full list of supported variables.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProvider(StrEnum):
    GOOGLE = "google"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"


_DEFAULT_MODELS: dict[LLMProvider, str] = {
    LLMProvider.GOOGLE: "gemini-2.0-flash",
    LLMProvider.OPENAI: "gpt-4o-mini",
    LLMProvider.ANTHROPIC: "claude-3-5-sonnet-latest",
    LLMProvider.OLLAMA: "qwen2.5-coder",
}


class Settings(BaseSettings):
    """Central, validated configuration object.

    Instantiate once via :func:`get_settings` rather than constructing directly,
    so the whole process shares one (cached) view of the environment.
    """

    model_config = SettingsConfigDict(
        env_prefix="ARGUS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # The provider API key fields declare an unprefixed alias (GOOGLE_API_KEY,
        # not ARGUS_GOOGLE_API_KEY) so they load from each provider's own
        # standard env var. `populate_by_name` additionally allows constructing
        # `Settings(google_api_key=...)` by field name, which callers (and
        # tests) do throughout this codebase.
        populate_by_name=True,
    )

    llm_provider: LLMProvider = LLMProvider.GOOGLE
    llm_model: str | None = None
    llm_temperature: float = 0.1
    llm_max_retries: int = 3

    google_api_key: str | None = Field(default=None, alias="GOOGLE_API_KEY")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")

    chroma_dir: Path = Path(".argus/chroma")
    embedding_provider: LLMProvider | None = None
    embedding_model: str | None = None

    max_context_expansion_rounds: int = 2
    max_files_per_review: int = 60
    retrieval_top_k: int = 12

    log_level: str = "INFO"

    def resolved_model(self) -> str:
        return self.llm_model or _DEFAULT_MODELS[self.llm_provider]

    def resolved_embedding_provider(self) -> LLMProvider:
        return self.embedding_provider or self.llm_provider


def get_settings() -> Settings:
    """Load settings fresh from the environment.

    Deliberately uncached: CLI commands like ``argus config`` and tests that
    monkeypatch environment variables both expect to see current values rather
    than a value frozen at first import.
    """
    return Settings()
