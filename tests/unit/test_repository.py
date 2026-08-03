from __future__ import annotations

from pathlib import Path

import pytest

from argus.models.diff import ChangeType
from argus.tools.repository import RepositoryError, RepositoryLoader, parse_unified_diff


def test_diff_between_two_commits(temp_git_repo: Path) -> None:
    loader = RepositoryLoader(temp_git_repo)
    diff = loader.diff("HEAD~1", "HEAD")

    assert diff.total_files_changed == 1
    file_diff = diff.files[0]
    assert file_diff.path == "pkg/a.py"
    assert file_diff.change_type == ChangeType.MODIFIED
    assert file_diff.language == "python"
    assert file_diff.additions > 0
    assert file_diff.deletions > 0


def test_read_file_at_ref(temp_git_repo: Path) -> None:
    loader = RepositoryLoader(temp_git_repo)
    content = loader.read_file_at_ref("pkg/b.py", "HEAD")
    assert content is not None
    assert "def helper" in content


def test_read_file_at_ref_missing_path_returns_none(temp_git_repo: Path) -> None:
    loader = RepositoryLoader(temp_git_repo)
    assert loader.read_file_at_ref("does/not/exist.py", "HEAD") is None


def test_list_files(temp_git_repo: Path) -> None:
    loader = RepositoryLoader(temp_git_repo)
    files = loader.list_files("HEAD")
    assert set(files) == {"pkg/__init__.py", "pkg/a.py", "pkg/b.py"}


def test_invalid_repo_path_raises(tmp_path: Path) -> None:
    not_a_repo = tmp_path / "not_a_repo"
    not_a_repo.mkdir()
    with pytest.raises(RepositoryError):
        RepositoryLoader(not_a_repo)


def test_unknown_ref_raises(temp_git_repo: Path) -> None:
    loader = RepositoryLoader(temp_git_repo)
    with pytest.raises(RepositoryError):
        loader.diff("nonexistent-ref", "HEAD")


def test_parse_unified_diff_added_and_removed_lines() -> None:
    patch = (
        "diff --git a/foo.py b/foo.py\n"
        "index 1111111..2222222 100644\n"
        "--- a/foo.py\n"
        "+++ b/foo.py\n"
        "@@ -1,2 +1,3 @@\n"
        " def foo():\n"
        "-    return 1\n"
        "+    return 2\n"
        "+    # extra\n"
    )
    files = parse_unified_diff(patch)
    assert len(files) == 1
    assert files[0].path == "foo.py"
    assert files[0].change_type == ChangeType.MODIFIED
    assert files[0].additions == 2
    assert files[0].deletions == 1


def test_parse_unified_diff_new_file() -> None:
    patch = (
        "diff --git a/new.py b/new.py\n"
        "new file mode 100644\n"
        "--- /dev/null\n"
        "+++ b/new.py\n"
        "@@ -0,0 +1,2 @@\n"
        "+def new():\n"
        "+    pass\n"
    )
    files = parse_unified_diff(patch)
    assert files[0].change_type == ChangeType.ADDED
    assert files[0].path == "new.py"
