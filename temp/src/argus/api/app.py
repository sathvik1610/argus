"""FastAPI service exposing Argus as an HTTP API.

Endpoints:
    POST /review   run a full review of a diff between two refs
    GET  /health   liveness check
    GET  /graph    the compiled review graph as a Mermaid diagram
    GET  /metrics  basic in-process counters
"""

from __future__ import annotations

import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from argus.config import get_settings
from argus.graph.workflow import build_graph_topology
from argus.services.logging import configure_logging, get_logger
from argus.services.review_service import run_review
from argus.tools.repository import RepositoryError

from .schemas import GraphResponse, HealthResponse, MetricsResponse, ReviewRequest, ReviewResponse

logger = get_logger(__name__)


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    configure_logging(get_settings().log_level)
    yield


app = FastAPI(
    title="Argus",
    description="AI-powered pull request review platform built on LangGraph.",
    version="0.1.0",
    lifespan=_lifespan,
)


class _Metrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.reviews_completed = 0
        self.reviews_failed = 0

    def record_success(self) -> None:
        with self._lock:
            self.reviews_completed += 1

    def record_failure(self) -> None:
        with self._lock:
            self.reviews_failed += 1


_metrics = _Metrics()


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


@app.get("/graph", response_model=GraphResponse)
def graph() -> GraphResponse:
    compiled = build_graph_topology()
    return GraphResponse(mermaid=compiled.get_graph().draw_mermaid())


@app.get("/metrics", response_model=MetricsResponse)
def metrics() -> MetricsResponse:
    return MetricsResponse(
        reviews_completed=_metrics.reviews_completed, reviews_failed=_metrics.reviews_failed
    )


@app.post("/review", response_model=ReviewResponse)
def review(request: ReviewRequest) -> ReviewResponse:
    """Run the full review graph. Synchronous and potentially slow (multiple
    LLM calls); FastAPI runs `def` endpoints in a thread pool automatically,
    so this does not block the event loop for concurrent requests."""
    settings = get_settings()
    try:
        state = run_review(request.repo_path, request.base_ref, request.head_ref, settings)
    except RepositoryError as exc:
        _metrics.record_failure()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        _metrics.record_failure()
        logger.error("review_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Review failed; see server logs.") from exc

    _metrics.record_success()
    return ReviewResponse(
        final_review=state["final_review"],
        strategy=state["strategy"],
        risk_assessment=state["risk_assessment"],
    )
