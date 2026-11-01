from __future__ import annotations

from pathlib import Path

import pytest

from argus.git_diff import Repo, RepoError, parse_patch


def test_diff_lists_changed_files_and_added_lines(sample_repo: Path) -> None:
    diff = Repo(sample_repo).diff("HEAD~1", "HEAD")
    assert diff.paths == ["payment.py"]
    # the new version adds lines 5-6 (changed pay body) and the refund function
    assert 5 in diff.files[0].added_lines
    assert max(diff.files[0].added_lines) == 10


def test_numbered_patch_shows_new_file_line_numbers(sample_repo: Path) -> None:
    diff = Repo(sample_repo).diff("HEAD~1", "HEAD")
    patch = diff.files[0].numbered_patch
    assert "   10 +    return balance + amount" in patch


def test_parse_patch_counts_context_lines() -> None:
    patch = "@@ -1,3 +1,3 @@\n a\n-b\n+B\n c\n"
    numbered, added, new_code = parse_patch(patch)
    assert added == [2]
    assert "    1  a" in numbered
    assert "    3  c" in numbered
    assert new_code == "a\nB\nc"


def test_render_truncates_long_diffs(sample_repo: Path) -> None:
    diff = Repo(sample_repo).diff("HEAD~1", "HEAD")
    text = diff.render(max_chars=30)
    assert text.endswith("[diff truncated] ...")


def test_read_file_and_list_files(sample_repo: Path) -> None:
    repo = Repo(sample_repo)
    assert set(repo.list_files("HEAD")) == {"wallet.py", "payment.py"}
    content = repo.read_file("HEAD", "wallet.py")
    assert content is not None and "MAX_WITHDRAWAL" in content
    assert repo.read_file("HEAD", "missing.py") is None


def test_bad_repo_and_bad_ref(sample_repo: Path, tmp_path: Path) -> None:
    with pytest.raises(RepoError):
        Repo(tmp_path / "nope")
    with pytest.raises(RepoError):
        Repo(sample_repo).diff("no-such-ref", "HEAD")
