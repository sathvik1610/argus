"""ChromaDB vector index of a repository's code chunks.

One Chroma collection per (repository, commit). Because the commit hash is part of
the collection name, an index is never stale: a new commit gets a fresh collection,
and re-reviewing the same commit reuses the embeddings already stored.
"""

from __future__ import annotations

import hashlib
import logging

import chromadb
from chromadb.config import Settings as ChromaSettings
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from argus.chunking import chunk_file, should_index_path, should_index_text
from argus.config import Settings
from argus.git_diff import Repo
from argus.models import Snippet

log = logging.getLogger(__name__)
BATCH_SIZE = 64  # chunks embedded per API call


def collection_name(repo: Repo, commit: str) -> str:
    digest = hashlib.sha1(f"{repo.path}|{commit}".encode()).hexdigest()[:16]
    return f"argus_{digest}"


def collect_chunks(repo: Repo, ref: str, max_chunks: int) -> list[Snippet]:
    """Read every indexable file at `ref` and split it into chunks."""
    chunks: list[Snippet] = []
    for path in repo.list_files(ref):
        if not should_index_path(path):
            continue
        text = repo.read_file(ref, path)
        if text is None or not should_index_text(text):
            continue
        chunks.extend(chunk_file(path, text))
        if len(chunks) >= max_chunks:
            log.warning("chunk limit reached (%d); the rest of the repo is not indexed", max_chunks)
            return chunks[:max_chunks]
    return chunks


class RepoIndex:
    def __init__(self, store: Chroma) -> None:
        self._store = store

    @classmethod
    def build(cls, repo: Repo, ref: str, settings: Settings, embeddings: Embeddings) -> RepoIndex:
        commit = repo.resolve(ref)
        settings.chroma_dir.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(
            path=str(settings.chroma_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        store = Chroma(
            collection_name=collection_name(repo, commit),
            embedding_function=embeddings,
            client=client,
        )
        if store.get(limit=1)["ids"]:
            return cls(store)  # this commit was indexed before

        chunks = collect_chunks(repo, ref, settings.max_chunks_to_index)
        for start in range(0, len(chunks), BATCH_SIZE):
            batch = chunks[start : start + BATCH_SIZE]
            store.add_documents(
                [_to_document(c) for c in batch],
                ids=[f"{c.file}:{c.start_line}:{c.end_line}" for c in batch],
            )
        return cls(store)

    def search(self, query: str, k: int) -> list[tuple[Snippet, float]]:
        """Nearest chunks to the query, with distance (lower means more similar)."""
        results = self._store.similarity_search_with_score(query, k=k)
        return [(_to_snippet(doc), float(score)) for doc, score in results]


def _to_document(chunk: Snippet) -> Document:
    # The file path and function name are embedded together with the code, so a query
    # that mentions "wallet" or "withdraw" is drawn towards the right chunk.
    header = f"# {chunk.file} {chunk.name or ''}".rstrip()
    metadata: dict[str, str | int] = {
        "file": chunk.file,
        "start_line": chunk.start_line,
        "end_line": chunk.end_line,
        "name": chunk.name or "",
    }
    return Document(page_content=f"{header}\n{chunk.code}", metadata=metadata)


def _to_snippet(doc: Document) -> Snippet:
    meta = doc.metadata
    return Snippet(
        file=meta["file"],
        start_line=meta["start_line"],
        end_line=meta["end_line"],
        name=meta["name"] or None,
        code=doc.page_content.split("\n", 1)[1],  # drop the header line added above
    )
