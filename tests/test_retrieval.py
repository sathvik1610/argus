from __future__ import annotations

from pathlib import Path

from argus.config import Settings
from argus.git_diff import Repo
from argus.index import RepoIndex, collect_chunks
from argus.retrieval import build_query, overlaps_change, retrieve
from tests.conftest import make_repo
from tests.fakes import FakeEmbeddings


def test_collect_chunks_skips_junk_files(tmp_path: Path) -> None:
    repo_path = make_repo(
        tmp_path / "r",
        [
            {
                "app.py": "def a():\n    return 1\n",
                "node_modules/x.js": "function x() {}\n",
                ".env": "KEY=abc\n",
                "secrets.py": "TOKEN = 'abc'\n",
                "notes.md": "# hi\n",
            }
        ],
    )
    files = {c.file for c in collect_chunks(Repo(repo_path), "HEAD", max_chunks=100)}
    assert files == {"app.py"}


def test_collect_chunks_respects_limit(tmp_path: Path) -> None:
    source = "\n".join(f"def f{i}():\n    return {i}\n" for i in range(30))
    repo_path = make_repo(tmp_path / "r", [{"many.py": source}])
    assert len(collect_chunks(Repo(repo_path), "HEAD", max_chunks=5)) == 5


def test_build_query_contains_path_and_identifiers(sample_repo: Path) -> None:
    diff = Repo(sample_repo).diff("HEAD~1", "HEAD")
    query = build_query(diff.files[0])
    assert "payment.py" in query
    assert "withdraw" in query
    assert "new_balance" in query
    assert "def" not in query.split("\n")[1].split()  # keywords are removed from identifiers


def test_retrieval_finds_related_code_outside_the_changed_file(
    sample_repo: Path, settings: Settings
) -> None:
    repo = Repo(sample_repo)
    index = RepoIndex.build(repo, "HEAD", settings, FakeEmbeddings())
    diff = repo.diff("HEAD~1", "HEAD")

    snippets = retrieve(diff, index, top_k=3)

    # the diff calls withdraw(), which is defined in wallet.py, a file the PR did not touch
    withdraw = [s for s in snippets if s.file == "wallet.py" and s.name == "withdraw"]
    assert withdraw, [(s.file, s.name) for s in snippets]
    assert withdraw[0].start_line == 4  # line information is kept
    assert "MAX_WITHDRAWAL" in withdraw[0].code


def test_retrieval_excludes_code_already_shown_in_the_diff(
    sample_repo: Path, settings: Settings
) -> None:
    repo = Repo(sample_repo)
    index = RepoIndex.build(repo, "HEAD", settings, FakeEmbeddings())
    diff = repo.diff("HEAD~1", "HEAD")
    for snippet in retrieve(diff, index, top_k=5):
        assert not overlaps_change(snippet, diff)


def test_retrieval_respects_top_k(sample_repo: Path, settings: Settings) -> None:
    repo = Repo(sample_repo)
    index = RepoIndex.build(repo, "HEAD", settings, FakeEmbeddings())
    diff = repo.diff("HEAD~1", "HEAD")
    assert len(retrieve(diff, index, top_k=1)) <= 1


def test_index_is_reused_for_the_same_commit(sample_repo: Path, settings: Settings) -> None:
    repo = Repo(sample_repo)

    class CountingEmbeddings(FakeEmbeddings):
        calls = 0

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            CountingEmbeddings.calls += 1
            return super().embed_documents(texts)

    RepoIndex.build(repo, "HEAD", settings, CountingEmbeddings())
    first = CountingEmbeddings.calls
    RepoIndex.build(repo, "HEAD", settings, CountingEmbeddings())
    assert first > 0
    assert CountingEmbeddings.calls == first  # second build embedded nothing
