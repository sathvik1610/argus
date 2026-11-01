from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from argus.config import Settings


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def make_repo(path: Path, commits: list[dict[str, str]]) -> Path:
    """Create a git repo with one commit per dict of {file path: content}."""
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q")
    git(path, "config", "user.email", "test@example.com")
    git(path, "config", "user.name", "Test")
    for i, files in enumerate(commits):
        for name, content in files.items():
            file = path / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(content, encoding="utf-8")
        git(path, "add", ".")
        git(path, "commit", "-q", "-m", f"commit {i}")
    return path


@pytest.fixture
def sample_repo(tmp_path: Path) -> Path:
    """wallet.py defines withdraw(); payment.py (changed in commit 2) calls it."""
    wallet = (
        "MAX_WITHDRAWAL = 500\n\n\n"
        "def withdraw(balance, amount):\n"
        "    if amount > MAX_WITHDRAWAL:\n"
        "        raise ValueError('over limit')\n"
        "    return balance - amount\n"
    )
    payment_v1 = "from wallet import withdraw\n\n\ndef pay(balance, amount):\n    return withdraw(balance, amount)\n"
    payment_v2 = (
        "from wallet import withdraw\n\n\n"
        "def pay(balance, amount):\n"
        "    new_balance = withdraw(balance, amount)\n"
        "    return new_balance\n\n\n"
        "def refund(balance, amount):\n"
        "    return balance + amount\n"
    )
    return make_repo(
        tmp_path / "repo",
        [{"wallet.py": wallet, "payment.py": payment_v1}, {"payment.py": payment_v2}],
    )


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(chroma_dir=tmp_path / "chroma", google_api_key="test-key")
