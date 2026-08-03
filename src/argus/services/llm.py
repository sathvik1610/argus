"""Provider-agnostic chat model and embedding factories.

Argus supports four LLM providers (Google Gemini, OpenAI, Anthropic, and local
Ollama) behind a single factory function so agents never import a
provider-specific class directly. Swapping providers is a config change, not a
code change.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from argus.config import LLMProvider, Settings

if TYPE_CHECKING:
    from langchain_core.embeddings import Embeddings
    from langchain_core.language_models import BaseChatModel


class UnsupportedProviderError(ValueError):
    """Raised when a provider has no registered factory."""


def build_chat_model(settings: Settings) -> BaseChatModel:
    """Construct the configured chat model, ready for structured output binding."""
    provider = settings.llm_provider
    model = settings.resolved_model()

    # The api_key/google_api_key parameters below are typed by their packages
    # as SecretStr (Anthropic) or a narrower Union (OpenAI); at runtime every
    # one of these classes accepts a plain `str | None` and coerces it, so the
    # mismatch is a stub inaccuracy rather than a real type error.
    if provider is LLMProvider.GOOGLE:
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=model,
            temperature=settings.llm_temperature,
            max_retries=settings.llm_max_retries,
            google_api_key=settings.google_api_key,
        )
    if provider is LLMProvider.OPENAI:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model,
            temperature=settings.llm_temperature,
            max_retries=settings.llm_max_retries,
            api_key=settings.openai_api_key,  # type: ignore[arg-type]
        )
    if provider is LLMProvider.ANTHROPIC:
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model_name=model,
            temperature=settings.llm_temperature,
            max_retries=settings.llm_max_retries,
            api_key=settings.anthropic_api_key,  # type: ignore[arg-type]
            timeout=120,
            stop=None,
        )
    if provider is LLMProvider.OLLAMA:
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=model,
            temperature=settings.llm_temperature,
            base_url=settings.ollama_base_url,
        )

    raise UnsupportedProviderError(f"No chat model factory registered for provider={provider!r}")


def build_embeddings(settings: Settings) -> Embeddings:
    """Construct the configured embedding model for repository indexing."""
    provider = settings.resolved_embedding_provider()
    model = settings.embedding_model

    if provider is LLMProvider.GOOGLE:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        return GoogleGenerativeAIEmbeddings(
            model=model or "models/text-embedding-004",
            google_api_key=settings.google_api_key,  # type: ignore[call-arg]
        )
    if provider is LLMProvider.OPENAI:
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(
            model=model or "text-embedding-3-small",
            api_key=settings.openai_api_key,  # type: ignore[arg-type]
        )
    if provider is LLMProvider.OLLAMA:
        from langchain_ollama import OllamaEmbeddings

        return OllamaEmbeddings(model=model or "nomic-embed-text", base_url=settings.ollama_base_url)
    if provider is LLMProvider.ANTHROPIC:
        # Anthropic does not offer an embeddings API; fall back to a local
        # sentence-transformer style model would add a heavy dependency, so we
        # default embeddings to Google when the chat provider is Anthropic and
        # no explicit embedding_provider was set.
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        return GoogleGenerativeAIEmbeddings(
            model=model or "models/text-embedding-004",
            google_api_key=settings.google_api_key,  # type: ignore[call-arg]
        )

    raise UnsupportedProviderError(f"No embeddings factory registered for provider={provider!r}")
