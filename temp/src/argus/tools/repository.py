"""Git repository access: loading, ref resolution, and diff extraction.

Wraps GitPython so the rest of the codebase only ever sees the domain models
in :mod:`argus.models.diff`, never raw ``git.Diff`` objects or patch text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import git
from git.exc import GitCommandError

from argus.models.diff import ChangeType, DiffHunk, DiffLine, FileDiff, PullRequestDiff
from argus.tools.language import detect_language

_HUNK_HEADER_RE = re.compile(
    r"^@@ -(?P<old_start>\d+)(?:,(?P<old_lines>\d+))? "
    r"\+(?P<new_start>\d+)(?:,(?P<new_lines>\d+))? @@(?P<rest>.*)$"
)


class RepositoryError(RuntimeError):
    """Raised for any repository access failure (bad ref, missing path, etc.)."""


@dataclass(frozen=True)
class RepositorySource:
    """Where a repository lives: an already-cloned local path, or a remote URL."""

    path: Path


class RepositoryLoader:
    """Loads a local git repository and extracts structured diffs from it."""

    def __init__(self, repo_path: str | Path):
        self.repo_path = Path(repo_path).resolve()
        try:
            self._repo = git.Repo(self.repo_path)
        except git.InvalidGitRepositoryError as exc:
            raise RepositoryError(f"{self.repo_path} is not a git repository") from exc
        except git.NoSuchPathError as exc:
            raise RepositoryError(f"path does not exist: {self.repo_path}") from exc

    @classmethod
    def clone(
        cls, url: str, destination: str | Path, *, depth: int | None = None
    ) -> RepositoryLoader:
        """Shallow-clone a remote repository into ``destination`` and load it."""
        destination = Path(destination)
        try:
            git.Repo.clone_from(url, destination, depth=depth)
        except GitCommandError as exc:
            raise RepositoryError(f"failed to clone {url}: {exc}") from exc
        return cls(destination)

    def resolve_ref(self, ref: str) -> str:
        try:
            return self._repo.commit(ref).hexsha
        except (git.BadName, ValueError) as exc:
            raise RepositoryError(f"unknown ref: {ref}") from exc

    def read_file_at_ref(self, path: str, ref: str = "HEAD") -> str | None:
        """Return file contents at a given ref, or None if the path doesn't exist there."""
        try:
            commit = self._repo.commit(ref)
            blob = commit.tree / path
            content: str = blob.data_stream.read().decode("utf-8", errors="replace")
            return content
        except (KeyError, git.BadName):
            return None

    def list_files(self, ref: str = "HEAD") -> list[str]:
        commit = self._repo.commit(ref)
        # GitPython types `traverse()` as a union of Tree/Blob/Submodule (and,
        # for compatibility mode, tuples); filtering on `.type == "blob"`
        # guarantees an actual Blob at runtime, which mypy can't narrow to here.
        return [
            str(item.path)  # type: ignore[union-attr]
            for item in commit.tree.traverse()
            if getattr(item, "type", None) == "blob"
        ]

    def diff(self, base_ref: str, head_ref: str = "HEAD") -> PullRequestDiff:
        """Compute the structured diff between two refs."""
        try:
            base_commit = self._repo.commit(base_ref)
            head_commit = self._repo.commit(head_ref)
        except (git.BadName, ValueError) as exc:
            raise RepositoryError(f"could not resolve refs {base_ref}..{head_ref}: {exc}") from exc

        git_diffs = base_commit.diff(head_commit, create_patch=True, R=False)
        files = [self._to_file_diff(d) for d in git_diffs]
        return PullRequestDiff(
            base_ref=base_commit.hexsha, head_ref=head_commit.hexsha, files=files
        )

    def diff_from_patch(
        self, patch_text: str, base_ref: str = "working-tree", head_ref: str = "HEAD"
    ) -> PullRequestDiff:
        """Parse a standalone unified diff (e.g. from ``git diff`` or a PR .patch file)."""
        files = parse_unified_diff(patch_text)
        return PullRequestDiff(base_ref=base_ref, head_ref=head_ref, files=files)

    @staticmethod
    def _to_file_diff(git_diff: git.Diff) -> FileDiff:
        path = git_diff.b_path or git_diff.a_path or "<unknown>"
        if git_diff.new_file:
            change_type = ChangeType.ADDED
        elif git_diff.deleted_file:
            change_type = ChangeType.DELETED
        elif getattr(git_diff, "renamed_file", False) or git_diff.a_path != git_diff.b_path:
            change_type = ChangeType.RENAMED
        else:
            change_type = ChangeType.MODIFIED

        if git_diff.diff is None:
            return FileDiff(
                path=path,
                old_path=git_diff.a_path if change_type == ChangeType.RENAMED else None,
                change_type=change_type,
                is_binary=True,
                language=detect_language(path),
            )

        raw_diff = git_diff.diff
        patch_text = (
            raw_diff.decode("utf-8", errors="replace") if isinstance(raw_diff, bytes) else raw_diff
        )
        hunks = _parse_hunks(patch_text)
        return FileDiff(
            path=path,
            old_path=git_diff.a_path if change_type == ChangeType.RENAMED else None,
            change_type=change_type,
            is_binary=False,
            language=detect_language(path),
            hunks=hunks,
        )


def parse_unified_diff(patch_text: str) -> list[FileDiff]:
    """Parse a multi-file unified diff into :class:`FileDiff` objects.

    Supports the standard ``diff --git a/x b/x`` format produced by
    ``git diff`` / GitHub's ``.patch`` export.
    """
    files: list[FileDiff] = []
    current_lines: list[str] = []
    current_a: str | None = None
    current_b: str | None = None

    def flush() -> None:
        if current_b is None and current_a is None:
            return
        path = current_b or current_a or "<unknown>"
        hunks = _parse_hunks("\n".join(current_lines))
        change_type = ChangeType.MODIFIED
        if current_a in (None, "/dev/null"):
            change_type = ChangeType.ADDED
        elif current_b in (None, "/dev/null"):
            change_type = ChangeType.DELETED
        elif current_a != current_b:
            change_type = ChangeType.RENAMED
        files.append(
            FileDiff(
                path=path,
                old_path=current_a if change_type == ChangeType.RENAMED else None,
                change_type=change_type,
                language=detect_language(path),
                hunks=hunks,
            )
        )

    for line in patch_text.splitlines():
        if line.startswith("diff --git "):
            flush()
            current_lines = []
            current_a = current_b = None
        elif line.startswith("--- "):
            current_a = _strip_ab_prefix(line[4:])
        elif line.startswith("+++ "):
            current_b = _strip_ab_prefix(line[4:])
        elif line.startswith("@@") or current_a is not None or current_b is not None:
            current_lines.append(line)
    flush()
    return files


def _strip_ab_prefix(raw: str) -> str | None:
    raw = raw.strip()
    if raw == "/dev/null":
        return None
    for prefix in ("a/", "b/"):
        if raw.startswith(prefix):
            return raw[len(prefix) :]
    return raw


def _parse_hunks(patch_text: str) -> list[DiffHunk]:
    hunks: list[DiffHunk] = []
    current: DiffHunk | None = None
    old_lineno = new_lineno = 0

    for line in patch_text.splitlines():
        match = _HUNK_HEADER_RE.match(line)
        if match:
            old_start = int(match.group("old_start"))
            new_start = int(match.group("new_start"))
            current = DiffHunk(
                header=line,
                old_start=old_start,
                old_lines=int(match.group("old_lines") or 1),
                new_start=new_start,
                new_lines=int(match.group("new_lines") or 1),
            )
            old_lineno, new_lineno = old_start, new_start
            hunks.append(current)
            continue

        if current is None:
            continue  # preamble (file headers) before the first hunk

        if line.startswith("+"):
            current.lines.append(DiffLine(kind="+", content=line[1:], new_lineno=new_lineno))
            new_lineno += 1
        elif line.startswith("-"):
            current.lines.append(DiffLine(kind="-", content=line[1:], old_lineno=old_lineno))
            old_lineno += 1
        elif line.startswith("\\"):
            continue  # "\ No newline at end of file"
        else:
            content = line[1:] if line.startswith(" ") else line
            current.lines.append(
                DiffLine(kind=" ", content=content, old_lineno=old_lineno, new_lineno=new_lineno)
            )
            old_lineno += 1
            new_lineno += 1

    return hunks
