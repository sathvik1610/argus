"""Chroma-backed semantic index over a repository's code chunks.

One local, on-disk Chroma collection per repository (keyed by a hash of its
resolved path), holding one embedded document per :class:`CodeChunk`. This is
the "semantic search" leg of retrieval; it's combined with AST-aware chunking
(what gets embedded) and import-graph ranking (which files are worth
embedding at all) rather than relied on alone — pure embedding similarity
misses structurally-obvious relevance like "this is the function the diff
directly modified".
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

from langchain_core.documents import Document

from argus.config import Settings
from argus.models.chunk import ChunkKind, CodeChunk
from argus.services.llm import build_embeddings

if TYPE_CHECKING:
    from langchain_core.embeddings import Embeddings


def collection_id_for(repo_path: str | Path) -> str:
    resolved = str(Path(repo_path).resolve())
    return hashlib.sha256(resolved.encode("utf-8")).hexdigest()[:16]


def _chunk_to_document(chunk: CodeChunk) -> Document:
    metadata: dict[str, Any] = {
        "file_path": chunk.file_path,
        "kind": chunk.kind.value,
        "start_line": chunk.start_line,
        "end_line": chunk.end_line,
    }
    if chunk.language:
        metadata["language"] = chunk.language
    if chunk.name:
        metadata["name"] = chunk.name
    if chunk.parent_name:
        metadata["parent_name"] = chunk.parent_name
    return Document(page_content=chunk.code, metadata=metadata)


def _document_to_chunk(doc: Document) -> CodeChunk:
    meta = doc.metadata
    return CodeChunk(
        file_path=meta["file_path"],
        language=meta.get("language"),
        kind=ChunkKind(meta["kind"]),
        name=meta.get("name"),
        parent_name=meta.get("parent_name"),
        start_line=meta["start_line"],
        end_line=meta["end_line"],
        code=doc.page_content,
    )


class RepositoryIndex:
    """Semantic index for a single repository's code chunks."""

    def __init__(
        self,
        settings: Settings,
        repo_path: str | Path,
        embeddings: "Embeddings | None" = None,
    ) -> None:
        from langchain_chroma import Chroma

        self.repo_path = Path(repo_path)
        self.collection_id = collection_id_for(self.repo_path)
        self._embeddings = embeddings or build_embeddings(settings)
        settings.chroma_dir.mkdir(parents=True, exist_ok=True)
        self._store = Chroma(
            collection_name=f"argus_{self.collection_id}",
            embedding_function=self._embeddings,
            persist_directory=str(settings.chroma_dir),
        )

    def index_chunks(self, chunks: list[CodeChunk]) -> int:
        """Upsert chunks into the index. Returns the number indexed."""
        if not chunks:
            return 0
        documents = [_chunk_to_document(c) for c in chunks]
        ids = [c.chunk_id for c in chunks]
        self._store.add_documents(documents, ids=ids)
        return len(chunks)

    def search(
        self, query: str, *, k: int = 8, file_paths: list[str] | None = None
    ) -> list[CodeChunk]:
        """Semantic similarity search, optionally restricted to a set of files."""
        where = {"file_path": {"$in": file_paths}} if file_paths else None
        results = self._store.similarity_search(query, k=k, filter=where)
        return [_document_to_chunk(d) for d in results]

    def chunk_count(self) -> int:
        # Chroma's public API doesn't expose collection size directly; the
        # underlying client does. Acceptable coupling to a private attribute
        # given the langchain-chroma wrapper offers no stable equivalent.
        return self._store._collection.count()  # type: ignore[attr-defined]
