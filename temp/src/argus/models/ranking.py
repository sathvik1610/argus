from __future__ import annotations

from pydantic import BaseModel


class RankedFile(BaseModel):
    path: str
    score: float
    reasons: list[str]
