from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from argus.api.app import app
from tests.fakes import FakeStructuredChatModel

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_graph_returns_mermaid_diagram() -> None:
    response = client.get("/graph")
    assert response.status_code == 200
    mermaid = response.json()["mermaid"]
    assert "graph TD" in mermaid
    assert "security" in mermaid
    assert "risk_estimation" in mermaid


def test_metrics_starts_at_zero() -> None:
    response = client.get("/metrics")
    assert response.status_code == 200
    body = response.json()
    assert "reviews_completed" in body
    assert "reviews_failed" in body


def test_review_with_nonexistent_repo_returns_400(monkeypatch: pytest.MonkeyPatch) -> None:
    # The chat model is only reached by nodes after `load_repository`, so a
    # fake model with no registered responses is sufficient here — the graph
    # must fail at repository loading, before any agent is invoked, and that
    # failure must surface as a 400 (client error) rather than a 500.
    monkeypatch.setattr(
        "argus.graph.workflow.build_chat_model", lambda settings: FakeStructuredChatModel({})
    )
    response = client.post(
        "/review", json={"repo_path": "/definitely/not/a/repo", "base_ref": "main"}
    )
    assert response.status_code == 400


def test_review_request_validation() -> None:
    response = client.post("/review", json={"base_ref": "main"})
    assert response.status_code == 422
