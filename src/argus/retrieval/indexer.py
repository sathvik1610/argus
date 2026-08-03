"""Ties together file loading, AST chunking, import graph construction, and
vector indexing into a single repository-indexing pass.

This is the concrete implementation behind the graph's "Repository Indexer"
node. It deliberately reads every source file's content exactly once and
reuses it for both the import graph and the chunk embeddings, since git blob
reads are the dominant cost for large repositories.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx

from argus.retrieval.ast_chunker import chunk_file
from argus.retrieval.import_graph import build_import_graph
from argus.retrieval.vector_store import RepositoryIndex
from argus.services.logging import get_logger
from argus.tools.language import is_source_code
from argus.tools.repository import RepositoryLoader

logger = get_logger(__name__)


@dataclass
class IndexResult:
    files_scanned: int
    files_indexed: int
    chunks_indexed: int
    import_graph: nx.DiGraph
    file_contents: dict[str, str] = field(default_factory=dict)


def collect_source_files(loader: RepositoryLoader, ref: str = "HEAD") -> dict[str, str]:
    """Read every source-code file in the repo at ``ref`` into memory."""
    contents: dict[str, str] = {}
    for path in loader.list_files(ref):
        if not is_source_code(path):
            continue
        text = loader.read_file_at_ref(path, ref)
        if text is not None:
            contents[path] = text
    return contents


def index_repository(
    loader: RepositoryLoader,
    index: RepositoryIndex,
    ref: str = "HEAD",
    *,
    max_file_bytes: int = 500_000,
) -> IndexResult:
    """Chunk and embed every source file at ``ref``, and build the import graph.

    Files larger than ``max_file_bytes`` are skipped for embedding (they are
    almost always generated/vendored code) but still appear as graph nodes.
    """
    file_contents = collect_source_files(loader, ref)
    import_graph = build_import_graph(file_contents)

    files_indexed = 0
    total_chunks = 0
    for path, source in file_contents.items():
        if len(source.encode("utf-8")) > max_file_bytes:
            logger.debug("skip_large_file", path=path, bytes=len(source))
            continue
        from argus.tools.language import detect_language

        chunks = chunk_file(path, source, detect_language(path))
        indexed = index.index_chunks(chunks)
        if indexed:
            files_indexed += 1
            total_chunks += indexed

    logger.info(
        "repository_indexed",
        files_scanned=len(file_contents),
        files_indexed=files_indexed,
        chunks_indexed=total_chunks,
    )
    return IndexResult(
        files_scanned=len(file_contents),
        files_indexed=files_indexed,
        chunks_indexed=total_chunks,
        import_graph=import_graph,
        file_contents=file_contents,
    )
