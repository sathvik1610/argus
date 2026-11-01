"""FastAPI app: POST /review and GET /health.

Run it with:  uvicorn argus.api:app
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from argus.config import ConfigError, Settings
from argus.git_diff import RepoError
from argus.models import Report
from argus.service import review_repo

log = logging.getLogger(__name__)
app = FastAPI(title="Argus", description="RAG-enhanced multi-agent pull request reviewer")


class ReviewRequest(BaseModel):
    repo_path: str
    base: str
    head: str = "HEAD"
    rag: bool = True


class PathNotAllowed(Exception):
    pass


def check_repo_path(path: str, settings: Settings) -> Path:
    """Only allow repositories inside the folders listed in ARGUS_ALLOWED_REPO_DIRS."""
    allowed = settings.allowed_dirs()
    if not allowed:
        raise PathNotAllowed("No safe directories configured. Set ARGUS_ALLOWED_REPO_DIRS.")
    resolved = Path(path).resolve()  # resolves '..' and symlinks before comparing
    if not any(resolved == root or resolved.is_relative_to(root) for root in allowed):
        raise PathNotAllowed("Repository path is outside the allowed directories.")
    return resolved


# Dependencies, so tests can swap in a fake reviewer or different settings.
def get_settings() -> Settings:
    return Settings()


def get_reviewer() -> Callable[..., Report]:
    return review_repo


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# A plain `def` endpoint (not `async def`) runs in a thread pool, so one slow review
# (several LLM calls) does not block other requests.
@app.post("/review", response_model=Report)
def review(
    request: ReviewRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    reviewer: Annotated[Callable[..., Report], Depends(get_reviewer)],
) -> Report:
    try:
        repo_path = check_repo_path(request.repo_path, settings)
        return reviewer(
            str(repo_path), request.base, request.head, rag=request.rag, settings=settings
        )
    except PathNotAllowed as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RepoError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("review failed")
        raise HTTPException(status_code=500, detail="Review failed; see server logs.") from exc
