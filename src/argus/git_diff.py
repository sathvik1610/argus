"""Reads a git repository: the diff between two refs, and file contents at a ref."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import git

HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


class RepoError(Exception):
    """Bad repo path or unknown ref."""


@dataclass
class ChangedFile:
    path: str
    numbered_patch: str  # the patch with new-file line numbers added, for the LLM
    added_lines: list[int]  # new-file line numbers of every added line


@dataclass
class Diff:
    base: str
    head: str
    files: list[ChangedFile]

    @property
    def paths(self) -> list[str]:
        return [f.path for f in self.files]

    def render(self, max_chars: int) -> str:
        """The whole diff as text for the prompt, cut off at max_chars."""
        parts = [f"### {f.path}\n{f.numbered_patch}" for f in self.files]
        text = "\n\n".join(parts)
        if len(text) > max_chars:
            text = text[:max_chars] + "\n... [diff truncated] ..."
        return text


def parse_patch(patch: str) -> tuple[str, list[int]]:
    """Add line numbers to a patch. Returns (numbered_patch, added_line_numbers)."""
    out: list[str] = []
    added: list[int] = []
    new_line = 0
    for line in patch.splitlines():
        match = HUNK_RE.match(line)
        if match:
            new_line = int(match.group(1))
            out.append(line)
        elif line.startswith("+"):
            out.append(f"{new_line:>5} {line}")
            added.append(new_line)
            new_line += 1
        elif line.startswith("-"):
            out.append(f"      {line}")
        elif line.startswith("\\"):
            continue  # "\ No newline at end of file"
        else:
            out.append(f"{new_line:>5} {line}")
            new_line += 1
    return "\n".join(out), added


class Repo:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve()
        try:
            self._repo = git.Repo(self.path)
        except (git.InvalidGitRepositoryError, git.NoSuchPathError) as exc:
            raise RepoError(f"not a git repository: {self.path}") from exc

    def resolve(self, ref: str) -> str:
        """Turn a branch/tag/commit into a full commit hash."""
        try:
            return str(self._repo.commit(ref).hexsha)
        except (git.BadName, ValueError) as exc:
            raise RepoError(f"unknown ref: {ref}") from exc

    def diff(self, base: str, head: str) -> Diff:
        base_commit = self._repo.commit(self.resolve(base))
        head_commit = self._repo.commit(self.resolve(head))
        files: list[ChangedFile] = []
        for item in base_commit.diff(head_commit, create_patch=True, R=False):
            raw = item.diff
            patch = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else (raw or "")
            if "@@" not in patch:
                continue  # binary file or a pure rename: nothing to review
            numbered, added = parse_patch(patch)
            files.append(ChangedFile(item.b_path or item.a_path or "?", numbered, added))
        return Diff(base_commit.hexsha, head_commit.hexsha, files)

    def list_files(self, ref: str) -> list[str]:
        commit = self._repo.commit(self.resolve(ref))
        return [
            str(getattr(b, "path", ""))
            for b in commit.tree.traverse()
            if getattr(b, "type", "") == "blob"
        ]

    def read_file(self, ref: str, path: str) -> str | None:
        try:
            blob = self._repo.commit(self.resolve(ref)).tree / path
            return str(blob.data_stream.read().decode("utf-8", errors="replace"))
        except KeyError:
            return None
