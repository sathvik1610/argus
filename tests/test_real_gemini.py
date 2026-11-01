"""Tests that call the REAL Gemini API (chat and embeddings).

Every other test in this project uses a fake model. These are the only ones that talk
to Google, so they are skipped unless a real GOOGLE_API_KEY is configured. Run them with:

    uv run pytest tests/test_real_gemini.py -v

They check that the whole pipeline works end to end (structured output parsing,
embeddings, retrieval, merging). They do NOT check review quality: model answers vary,
so they only assert on the shape of the result. Quality is what `evaluation/` measures.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from argus.config import PLACEHOLDER_KEY, Settings
from argus.service import review_repo
from evaluation.run import build_repo
from evaluation.scenarios import ALL_SCENARIOS

_KEY = Settings().google_api_key
HAS_REAL_KEY = bool(_KEY) and _KEY != PLACEHOLDER_KEY

pytestmark = pytest.mark.skipif(not HAS_REAL_KEY, reason="no real GOOGLE_API_KEY configured")


def scenario_repo(scenario_id: str, tmp_path: Path) -> Path:
    scenario = next(s for s in ALL_SCENARIOS if s.id == scenario_id)
    return build_repo(scenario, tmp_path / scenario_id)


def test_real_review_without_rag(tmp_path: Path) -> None:
    repo = scenario_repo("sec_sql_injection", tmp_path)
    settings = Settings(chroma_dir=tmp_path / "chroma")
    report = review_repo(str(repo), "HEAD~1", "HEAD", rag=False, settings=settings)
    assert report.rag_enabled is False
    assert report.tokens_used > 0  # the API reported real token usage
    assert 0 <= report.risk_score <= 100


def test_real_review_with_rag_retrieves_cross_file_context(tmp_path: Path) -> None:
    repo = scenario_repo("cor_cents_vs_dollars", tmp_path)
    settings = Settings(chroma_dir=tmp_path / "chroma")
    report = review_repo(str(repo), "HEAD~1", "HEAD", rag=True, settings=settings)
    assert report.rag_enabled is True
    # pricing.py was not changed by the PR, so seeing it means real embeddings and
    # similarity search worked.
    assert any(s.file == "pricing.py" for s in report.retrieved_context)
