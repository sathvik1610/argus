from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from argus.config import Settings


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def temp_git_repo(tmp_path: Path) -> Path:
    """A tiny two-commit repo: pkg/b.py defines helper(), pkg/a.py imports and
    calls it. The second commit changes a.py's use() and adds a new function
    with an obvious nested-loop performance smell, for reviewer tests."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")

    pkg = repo / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "b.py").write_text("def helper():\n    return 1\n")
    (pkg / "a.py").write_text("from pkg.b import helper\n\n\ndef use():\n    return helper()\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "init")

    (pkg / "a.py").write_text(
        "from pkg.b import helper\n\n\n"
        "def use():\n    return helper() + 1\n\n\n"
        "def new_fn(items):\n    for i in items:\n        for j in items:\n            pass\n"
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "change")

    return repo


class FakeEmbeddings:
    """Deterministic, dependency-free stand-in for a real embeddings model."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(t) % 7), float(i % 5)] for i, t in enumerate(texts)]

    def embed_query(self, text: str) -> list[float]:
        return [float(len(text) % 7), 0.0]


@pytest.fixture
def fake_embeddings() -> FakeEmbeddings:
    return FakeEmbeddings()


@pytest.fixture
def settings(tmp_path: Path) -> Iterator[Settings]:
    yield Settings(chroma_dir=tmp_path / ".argus" / "chroma", max_context_expansion_rounds=1)
