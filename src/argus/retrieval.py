"""Turns a diff into search queries and picks the most useful related code (RAG)."""

from __future__ import annotations

import keyword
import re

from argus.git_diff import ChangedFile, Diff
from argus.index import RepoIndex
from argus.models import Snippet

IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
COMMON_WORDS = set(keyword.kwlist) | {
    "self", "this", "const", "let", "var", "function", "return", "public", "private", "static",
    "void", "int", "string", "true", "false", "null", "new", "import", "from", "def", "class",
}  # fmt: skip
MAX_IDENTIFIERS = 30
MAX_CODE_CHARS = 600
CANDIDATES_PER_QUERY = 10


def build_query(changed: ChangedFile) -> str:
    """One query per changed file: its path, the identifiers it uses, and the new code.

    Identifiers (function and variable names) matter most: if the diff calls
    `withdraw(...)`, we want the chunk that defines `withdraw`.
    """
    seen: dict[str, None] = {}  # a dict keeps first-seen order and removes duplicates
    for word in IDENTIFIER.findall(changed.new_code):
        if word not in COMMON_WORDS:
            seen.setdefault(word)
    identifiers = " ".join(list(seen)[:MAX_IDENTIFIERS])
    return f"{changed.path}\n{identifiers}\n{changed.new_code[:MAX_CODE_CHARS]}"


def overlaps_change(snippet: Snippet, diff: Diff) -> bool:
    """True if the snippet is code the diff already shows (so it adds no new context)."""
    for changed in diff.files:
        if changed.path == snippet.file and any(
            snippet.start_line <= n <= snippet.end_line for n in changed.added_lines
        ):
            return True
    return False


def retrieve(diff: Diff, index: RepoIndex, top_k: int) -> list[Snippet]:
    """Return up to `top_k` snippets related to the change, best match first."""
    best: dict[tuple[str, int], tuple[float, Snippet]] = {}
    for changed in diff.files:
        for snippet, distance in index.search(build_query(changed), CANDIDATES_PER_QUERY):
            if overlaps_change(snippet, diff):
                continue
            key = (snippet.file, snippet.start_line)
            if key not in best or distance < best[key][0]:
                best[key] = (distance, snippet)
    ranked = sorted(best.values(), key=lambda pair: pair[0])
    return [snippet for _, snippet in ranked[:top_k]]
