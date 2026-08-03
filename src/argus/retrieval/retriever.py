"""Combines file ranking + AST chunking + semantic search into the retrieval
step the graph calls at "Retrieve Relevant Files" and "Retrieve More Files".

Two complementary sources of chunks feed a review:

1. **Touched chunks** — the exact functions/methods the diff's hunks fall
   inside, found via AST chunking of the changed files. These are non-
   negotiable: an agent cannot review what it cannot see.
2. **Related chunks** — semantically similar code elsewhere in the repo
   (callers, similar patterns, shared utilities), found via vector search
   restricted to files the import graph ranked as relevant. This is what lets
   agents catch things like "this new validation duplicates logic already in
   utils/validate.py" without reading the whole repository.
"""

from __future__ import annotations

import networkx as nx

from argus.config import Settings
from argus.models.chunk import CodeChunk
from argus.models.context import RetrievedContext
from argus.models.diff import PullRequestDiff
from argus.retrieval.ast_chunker import chunk_file
from argus.retrieval.ranking import rank_files
from argus.retrieval.vector_store import RepositoryIndex

_MAX_QUERY_CHARS = 4000


class ContextRetriever:
    def __init__(
        self,
        index: RepositoryIndex,
        import_graph: nx.DiGraph,
        file_contents: dict[str, str],
        settings: Settings,
    ) -> None:
        self._index = index
        self._graph = import_graph
        self._file_contents = file_contents
        self._settings = settings

    def retrieve_for_diff(self, diff: PullRequestDiff) -> RetrievedContext:
        ranked_files = rank_files(
            self._graph, diff.changed_paths, limit=self._settings.max_files_per_review
        )
        ranked_paths = [r.path for r in ranked_files]

        touched_chunks = self._touched_chunks(diff)
        touched_ids = {c.chunk_id for c in touched_chunks}

        query = _build_diff_query(diff)
        semantic_hits = (
            self._index.search(query, k=self._settings.retrieval_top_k, file_paths=ranked_paths)
            if query
            else []
        )
        related_chunks = [c for c in semantic_hits if c.chunk_id not in touched_ids]

        return RetrievedContext(
            ranked_files=ranked_files, touched_chunks=touched_chunks, related_chunks=related_chunks
        )

    def expand(self, context: RetrievedContext, follow_up_query: str, *, k: int = 6) -> RetrievedContext:
        """Pull in additional chunks matching a follow-up query (need-more-context loop)."""
        existing_ids = {c.chunk_id for c in context.combined_chunks}
        hits = self._index.search(follow_up_query[:_MAX_QUERY_CHARS], k=k)
        new_chunks = [c for c in hits if c.chunk_id not in existing_ids]
        return context.model_copy(update={"related_chunks": [*context.related_chunks, *new_chunks]})

    def _touched_chunks(self, diff: PullRequestDiff) -> list[CodeChunk]:
        touched: list[CodeChunk] = []
        for file_diff in diff.files:
            source = self._file_contents.get(file_diff.path)
            if source is None or file_diff.is_binary:
                continue
            changed_lines = {
                line for hunk in file_diff.hunks for line in hunk.added_line_numbers()
            }
            if not changed_lines:
                continue
            for chunk in chunk_file(file_diff.path, source, file_diff.language):
                if any(chunk.start_line <= ln <= chunk.end_line for ln in changed_lines):
                    touched.append(chunk)
        return touched


def _build_diff_query(diff: PullRequestDiff) -> str:
    parts: list[str] = []
    for file_diff in diff.files:
        added = [
            line.content
            for hunk in file_diff.hunks
            for line in hunk.lines
            if line.kind == "+"
        ]
        if added:
            parts.append(f"{file_diff.path}:\n" + "\n".join(added[:40]))
    return "\n\n".join(parts)[:_MAX_QUERY_CHARS]
