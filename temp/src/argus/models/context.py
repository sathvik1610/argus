from __future__ import annotations

from pydantic import BaseModel

from argus.models.chunk import CodeChunk
from argus.models.ranking import RankedFile


class RetrievedContext(BaseModel):
    """Everything retrieval decided is worth showing the review agents."""

    ranked_files: list[RankedFile]
    touched_chunks: list[CodeChunk]
    related_chunks: list[CodeChunk]

    @property
    def combined_chunks(self) -> list[CodeChunk]:
        return [*self.touched_chunks, *self.related_chunks]

    def render(self, *, max_chunks: int | None = None) -> str:
        """Render retrieved chunks as a single text block for prompt injection."""
        chunks = self.combined_chunks
        if max_chunks is not None:
            chunks = chunks[:max_chunks]

        touched_ids = {c.chunk_id for c in self.touched_chunks}
        sections = []
        for chunk in chunks:
            label = "CHANGED" if chunk.chunk_id in touched_ids else "RELATED"
            header = f"# [{label}] {chunk.file_path} :: {chunk.qualified_name} (L{chunk.start_line}-{chunk.end_line})"
            sections.append(f"{header}\n{chunk.code}")
        return "\n\n".join(sections)
