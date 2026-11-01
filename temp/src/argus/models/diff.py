"""Domain models describing a parsed pull request / git diff.

These are the atoms the rest of the pipeline (indexing, ranking, retrieval,
review agents) reasons about, instead of raw diff text.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class ChangeType(StrEnum):
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"


class DiffLine(BaseModel):
    """A single line within a hunk."""

    kind: str = Field(description="'+' added, '-' removed, ' ' context")
    content: str
    new_lineno: int | None = None
    old_lineno: int | None = None


class DiffHunk(BaseModel):
    header: str
    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    lines: list[DiffLine] = Field(default_factory=list)

    def added_line_numbers(self) -> list[int]:
        return [ln.new_lineno for ln in self.lines if ln.kind == "+" and ln.new_lineno is not None]

    def removed_line_numbers(self) -> list[int]:
        return [ln.old_lineno for ln in self.lines if ln.kind == "-" and ln.old_lineno is not None]


class FileDiff(BaseModel):
    path: str
    old_path: str | None = None
    change_type: ChangeType
    is_binary: bool = False
    language: str | None = None
    hunks: list[DiffHunk] = Field(default_factory=list)

    @property
    def additions(self) -> int:
        return sum(len(h.added_line_numbers()) for h in self.hunks)

    @property
    def deletions(self) -> int:
        return sum(len(h.removed_line_numbers()) for h in self.hunks)

    @property
    def total_changes(self) -> int:
        return self.additions + self.deletions


class PullRequestDiff(BaseModel):
    """The full set of changes between two refs."""

    base_ref: str
    head_ref: str
    files: list[FileDiff] = Field(default_factory=list)

    @property
    def changed_paths(self) -> list[str]:
        return [f.path for f in self.files]

    @property
    def total_additions(self) -> int:
        return sum(f.additions for f in self.files)

    @property
    def total_deletions(self) -> int:
        return sum(f.deletions for f in self.files)

    @property
    def total_files_changed(self) -> int:
        return len(self.files)
