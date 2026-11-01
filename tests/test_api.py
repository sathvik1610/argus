from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from argus.api import app, get_reviewer, get_settings
from argus.config import ConfigError, Settings
from argus.git_diff import RepoError
from argus.merge import build_report
from argus.models import Report


@pytest.fixture
def client() -> Iterator[TestClient]:
    yield TestClient(app)
    app.dependency_overrides.clear()


def configure(allowed: Path | None, reviewer: Callable[..., Report] | None = None) -> None:
    settings = Settings(allowed_repo_dirs=str(allowed) if allowed else "")
    app.dependency_overrides[get_settings] = lambda: settings
    if reviewer is not None:
        app.dependency_overrides[get_reviewer] = lambda: reviewer


def ok_reviewer(*_args: Any, **_kwargs: Any) -> Report:
    return build_report([], [], 0)


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_review_returns_a_report(client: TestClient, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    seen: dict[str, Any] = {}

    def reviewer(path: str, base: str, head: str, **kwargs: Any) -> Report:
        seen.update(path=path, base=base, head=head, **kwargs)
        return build_report([], [], 5)

    configure(tmp_path, reviewer)
    response = client.post("/review", json={"repo_path": str(repo), "base": "main", "rag": False})
    assert response.status_code == 200
    body = response.json()
    assert set(body) >= {"summary", "findings", "severity_counts", "retrieved_context"}
    assert seen["base"] == "main"
    assert seen["head"] == "HEAD"  # default
    assert seen["rag"] is False


def test_review_refuses_paths_outside_allowed_dirs(client: TestClient, tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    configure(allowed, ok_reviewer)
    response = client.post("/review", json={"repo_path": str(tmp_path), "base": "main"})
    assert response.status_code == 403


def test_review_blocks_dotdot_escape(client: TestClient, tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    configure(allowed, ok_reviewer)
    sneaky = str(allowed / ".." / "..")
    assert client.post("/review", json={"repo_path": sneaky, "base": "x"}).status_code == 403


def test_review_refuses_everything_when_no_dirs_configured(
    client: TestClient, tmp_path: Path
) -> None:
    configure(None, ok_reviewer)
    response = client.post("/review", json={"repo_path": str(tmp_path), "base": "main"})
    assert response.status_code == 403
    assert "ARGUS_ALLOWED_REPO_DIRS" in response.json()["detail"]


@pytest.mark.parametrize(
    ("error", "status"),
    [(RepoError("unknown ref"), 400), (ConfigError("no key"), 503), (RuntimeError("boom"), 500)],
)
def test_errors_map_to_status_codes(
    client: TestClient, tmp_path: Path, error: Exception, status: int
) -> None:
    def failing(*_args: Any, **_kwargs: Any) -> Report:
        raise error

    configure(tmp_path, failing)
    response = client.post("/review", json={"repo_path": str(tmp_path), "base": "main"})
    assert response.status_code == status
    assert "boom" not in response.text  # internal error details are not leaked


def test_review_validates_input(client: TestClient, tmp_path: Path) -> None:
    configure(tmp_path, ok_reviewer)
    assert client.post("/review", json={"base": "main"}).status_code == 422
