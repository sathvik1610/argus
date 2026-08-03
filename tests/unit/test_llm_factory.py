from __future__ import annotations

import pytest

from argus.config import LLMProvider, Settings
from argus.services.llm import UnsupportedProviderError, build_chat_model, build_embeddings


def test_build_chat_model_google() -> None:
    settings = Settings(llm_provider=LLMProvider.GOOGLE, google_api_key="fake-key")
    model = build_chat_model(settings)
    assert model.model == "gemini-2.0-flash"


def test_build_chat_model_openai() -> None:
    settings = Settings(llm_provider=LLMProvider.OPENAI, openai_api_key="fake-key")
    model = build_chat_model(settings)
    assert "gpt-4o-mini" in model.model_name


def test_build_chat_model_anthropic() -> None:
    settings = Settings(llm_provider=LLMProvider.ANTHROPIC, anthropic_api_key="fake-key")
    model = build_chat_model(settings)
    assert model.model == "claude-3-5-sonnet-latest"


def test_build_chat_model_ollama_needs_no_api_key() -> None:
    settings = Settings(llm_provider=LLMProvider.OLLAMA)
    model = build_chat_model(settings)
    assert model.model == "qwen2.5-coder"


def test_resolved_model_override() -> None:
    settings = Settings(llm_provider=LLMProvider.GOOGLE, llm_model="gemini-2.5-pro", google_api_key="x")
    model = build_chat_model(settings)
    assert model.model == "gemini-2.5-pro"


def test_build_embeddings_google() -> None:
    settings = Settings(llm_provider=LLMProvider.GOOGLE, google_api_key="fake-key")
    embeddings = build_embeddings(settings)
    assert embeddings.model == "models/text-embedding-004"


def test_build_embeddings_anthropic_falls_back_to_google() -> None:
    # Anthropic has no embeddings API; embeddings should default to Google.
    settings = Settings(llm_provider=LLMProvider.ANTHROPIC, google_api_key="fake-key")
    embeddings = build_embeddings(settings)
    assert embeddings.model == "models/text-embedding-004"


def test_unsupported_provider_raises() -> None:
    settings = Settings(llm_provider=LLMProvider.GOOGLE, llm_model="explicit-model", google_api_key="x")
    # Force an unregistered provider value past validation to exercise the
    # factory's fallthrough branch (bypassing resolved_model()'s default-model
    # lookup by supplying an explicit llm_model).
    settings.llm_provider = "carrier-pigeon"  # type: ignore[assignment]
    with pytest.raises(UnsupportedProviderError):
        build_chat_model(settings)
