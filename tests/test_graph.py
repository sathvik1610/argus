from __future__ import annotations

import time
from pathlib import Path

import pytest

from argus.config import Settings
from argus.git_diff import RepoError
from argus.models import AgentOutput, Category, Finding, Severity
from argus.service import review_repo
from tests.fakes import FakeChatModel, FakeEmbeddings, by_category, category_of


def finding(category: Category, line: int = 10, severity: Severity = Severity.HIGH) -> Finding:
    return Finding(
        file="payment.py",
        line=line,
        category=category,
        severity=severity,
        description=f"{category.value} problem on line {line}",
        suggested_fix="fix",
    )


def test_full_graph_merges_findings_from_all_three_agents(
    sample_repo: Path, settings: Settings
) -> None:
    model = FakeChatModel(
        by_category(
            {
                Category.SECURITY: [finding(Category.SECURITY, 5)],
                Category.CORRECTNESS: [finding(Category.CORRECTNESS, 10)],
                Category.PERFORMANCE: [finding(Category.PERFORMANCE, 30, Severity.LOW)],
            }
        ),
        tokens=7,
    )
    report = review_repo(
        str(sample_repo),
        "HEAD~1",
        "HEAD",
        rag=False,
        settings=settings,
        model=model,
        embeddings=FakeEmbeddings(),
    )
    assert {f.category for f in report.findings} == set(Category)
    assert report.tokens_used == 21  # 3 agents x 7 tokens, added up by the reducer
    assert report.rag_enabled is False
    assert len(model.calls) == 3


def test_rag_adds_retrieved_context_to_every_agent_prompt(
    sample_repo: Path, settings: Settings
) -> None:
    model = FakeChatModel(by_category({}))
    report = review_repo(
        str(sample_repo),
        "HEAD~1",
        "HEAD",
        rag=True,
        settings=settings,
        model=model,
        embeddings=FakeEmbeddings(),
    )
    assert report.rag_enabled is True
    assert any(s.file == "wallet.py" for s in report.retrieved_context)
    for _system, user in model.calls:
        assert "<context>" in user
        assert "def withdraw" in user  # the code from the file the PR did not touch


def test_without_rag_prompts_have_no_context(sample_repo: Path, settings: Settings) -> None:
    model = FakeChatModel(by_category({}))
    review_repo(str(sample_repo), "HEAD~1", "HEAD", rag=False, settings=settings, model=model)
    for _system, user in model.calls:
        assert "<context>" not in user
        assert "<diff>" in user


def test_each_agent_gets_its_own_prompt(sample_repo: Path, settings: Settings) -> None:
    model = FakeChatModel(by_category({}))
    review_repo(str(sample_repo), "HEAD~1", "HEAD", rag=False, settings=settings, model=model)
    assert {category_of(system) for system, _ in model.calls} == set(Category)


def test_agents_run_in_parallel(sample_repo: Path, settings: Settings) -> None:
    delay = 0.4

    def slow(_system: str, _user: str) -> AgentOutput:
        time.sleep(delay)
        return AgentOutput()

    model = FakeChatModel(slow)
    start = time.perf_counter()
    review_repo(str(sample_repo), "HEAD~1", "HEAD", rag=False, settings=settings, model=model)
    elapsed = time.perf_counter() - start
    # Run one after another this would take at least 3 x 0.4 = 1.2s.
    assert elapsed < delay * 2.2, f"agents look sequential: {elapsed:.2f}s"


def test_empty_diff_makes_no_llm_calls(sample_repo: Path, settings: Settings) -> None:
    model = FakeChatModel(by_category({}))
    # comparing a commit with itself gives an empty diff
    report = review_repo(str(sample_repo), "HEAD", "HEAD", rag=True, settings=settings, model=model)
    assert report.findings == []
    assert report.rag_enabled is False  # nothing to retrieve for
    assert model.calls == []


def test_unknown_ref_fails_before_any_llm_call(sample_repo: Path, settings: Settings) -> None:
    model = FakeChatModel(by_category({}))
    with pytest.raises(RepoError):
        review_repo(str(sample_repo), "nope", "HEAD", settings=settings, model=model)
    assert model.calls == []
