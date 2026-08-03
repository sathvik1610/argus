"""Domain model for a semantically-meaningful piece of source code.

A :class:`CodeChunk` is the unit Argus embeds, ranks, and hands to review
agents — never a whole file. Whole files blow the context budget on anything
beyond a toy repo; function/method/class-sized chunks let retrieval be
precise about what an agent actually needs to see.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class ChunkKind(StrEnum):
    FUNCTION = "function"
    METHOD = "method"
    CLASS_HEADER = "class_header"
    MODULE = "module"


class CodeChunk(BaseModel):
    file_path: str
    language: str | None
    kind: ChunkKind
    name: str | None
    parent_name: str | None = None
    start_line: int
    end_line: int
    code: str

    @property
    def chunk_id(self) -> str:
        suffix = self.name or f"{self.start_line}-{self.end_line}"
        return f"{self.file_path}::{suffix}"

    @property
    def qualified_name(self) -> str:
        if self.parent_name and self.name:
            return f"{self.parent_name}.{self.name}"
        return self.name or self.file_path
