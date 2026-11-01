"""Builds the Gemini chat model and embedding model used by Argus."""

from __future__ import annotations

from typing import Any

from langchain_core.embeddings import Embeddings
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

from argus.config import Settings


def get_chat_model(settings: Settings) -> Any:
    # temperature=0 keeps reviews as repeatable as an LLM allows, which matters
    # when we compare "with RAG" against "without RAG".
    return ChatGoogleGenerativeAI(
        model=settings.llm_model,
        temperature=0,
        google_api_key=settings.require_api_key(),
        max_retries=2,
    )


def get_embeddings(settings: Settings) -> Embeddings:
    # The ignore below: installed type stubs lag the real constructor.
    return GoogleGenerativeAIEmbeddings(
        model=settings.embedding_model,
        google_api_key=settings.require_api_key(),  # type: ignore[call-arg]
    )
