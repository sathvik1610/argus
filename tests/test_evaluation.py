from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from argus.config import Settings
from argus.git_diff import Repo
from argus.models import AgentOutput, Category, Finding, Severity
from evaluation.run import build_repo, run_all, save, summarize
from evaluation.scenario import ExpectedBug, Scenario
from evaluation.scenarios import ALL_SCENARIOS
from evaluation.scoring import marker_line, matches, score_findings
from tests.fakes import FakeChatModel, FakeEmbeddings, category_of

# ---------- the scenarios themselves ----------


def test_there_are_12_to_15_scenarios_with_unique_ids() -> None:
    ids = [s.id for s in ALL_SCENARIOS]
    assert 12 <= len(ids) <= 15
    assert len(set(ids)) == len(ids)


def test_scenario_mix_matches_the_plan() -> None:
    kinds = Counter(s.kind for s in ALL_SCENARIOS)
    assert kinds["security"] >= 3
    assert kinds["correctness"] >= 3
    assert kinds["performance"] >= 2
    assert kinds["clean"] >= 3
    assert sum(s.needs_context for s in ALL_SCENARIOS) >= 3


def test_bug_scenarios_have_expected_bugs_and_clean_ones_do_not() -> None:
    for s in ALL_SCENARIOS:
        assert bool(s.expected) == (s.kind != "clean"), s.id


def test_every_marker_exists_in_the_pr_version_of_its_file() -> None:
    for s in ALL_SCENARIOS:
        for bug in s.expected:
            assert bug.file in s.pr_files, (s.id, bug.file)
            assert marker_line(s, bug) >= 1


def test_every_pr_changes_something() -> None:
    for s in ALL_SCENARIOS:
        for name, content in s.pr_files.items():
            assert s.base_files.get(name) != content, (s.id, name)


def test_context_scenarios_keep_the_needed_file_unchanged() -> None:
    """For cross-file bugs, the file holding the key information is not part of the PR."""
    for s in ALL_SCENARIOS:
        if s.needs_context:
            untouched = set(s.base_files) - set(s.pr_files)
            assert untouched, f"{s.id} has no file outside the PR to retrieve"


def test_scenarios_build_into_repos_whose_diff_is_the_pr(tmp_path: Path) -> None:
    for s in ALL_SCENARIOS:
        repo = Repo(build_repo(s, tmp_path / s.id))
        diff = repo.diff("HEAD~1", "HEAD")
        assert set(diff.paths) == set(s.pr_files), s.id
        for bug in s.expected:
            changed = next(f for f in diff.files if f.path == bug.file)
            assert marker_line(s, bug) in changed.added_lines, (s.id, bug.marker)


# ---------- scoring ----------

BUG = ExpectedBug("users.py", "WHERE name", ("injection", "parameteriz"))
SCENARIO = Scenario(
    id="demo",
    kind="security",
    description="demo",
    base_files={"users.py": "x = 1\n"},
    pr_files={"users.py": "x = 1\nq = 'WHERE name'\n"},
    expected=(BUG,),
)


def finding(
    file: str = "users.py", line: int | None = None, text: str = "something odd"
) -> Finding:
    return Finding(
        file=file,
        line=line,
        category=Category.SECURITY,
        severity=Severity.HIGH,
        description=text,
        suggested_fix="fix",
    )


def test_marker_line_is_found() -> None:
    assert marker_line(SCENARIO, BUG) == 2


def test_keyword_match_counts() -> None:
    assert matches(finding(text="Possible SQL injection"), BUG, 2)


def test_line_match_counts_within_tolerance() -> None:
    assert matches(finding(line=3, text="unrelated words"), BUG, 2)
    assert not matches(finding(line=20, text="unrelated words"), BUG, 2)


def test_wrong_file_never_matches() -> None:
    assert not matches(finding(file="other.py", line=2, text="injection"), BUG, 2)


def test_score_separates_found_missed_and_false_positives() -> None:
    caught = score_findings(
        SCENARIO, [finding(text="injection!"), finding(text="style nit", line=99)]
    )
    assert caught.found == ["WHERE name"]
    assert caught.missed == []
    assert len(caught.false_positives) == 1

    nothing = score_findings(SCENARIO, [])
    assert nothing.found == []
    assert nothing.missed == ["WHERE name"]


def test_every_finding_on_a_clean_change_is_a_false_positive() -> None:
    clean = Scenario("c", "clean", "c", {"a.py": "x\n"}, {"a.py": "y\n"})
    score = score_findings(clean, [finding(file="a.py"), finding(file="a.py", line=1)])
    assert len(score.false_positives) == 2


# ---------- the runner, with a fake model ----------


def sql_aware_model() -> FakeChatModel:
    """Reports the SQL injection in sec_sql_injection (security agent only), and also
    one made-up finding on the clean scenario, so false positives are exercised."""

    def respond(system: str, user: str) -> AgentOutput:
        if category_of(system) is not Category.SECURITY:
            return AgentOutput()
        if "WHERE name = '{name}'" in user:
            return AgentOutput(
                findings=[finding(file="users.py", line=9, text="SQL injection via f-string")]
            )
        if "Return the sum of all item prices" in user:
            return AgentOutput(findings=[finding(file="utils.py", line=1, text="nitpick")])
        return AgentOutput()

    return FakeChatModel(respond, tokens=11)


def test_run_all_evaluates_both_modes(tmp_path: Path) -> None:
    scenarios = [s for s in ALL_SCENARIOS if s.id in {"sec_sql_injection", "clean_rename_and_docs"}]
    settings = Settings(chroma_dir=tmp_path / "chroma", google_api_key="test-key")
    records = run_all(scenarios, settings, sql_aware_model(), FakeEmbeddings(), tmp_path / "repos")

    assert len(records) == 4  # 2 scenarios x (no RAG, RAG)
    assert {(r["scenario"], r["rag"]) for r in records} == {
        ("sec_sql_injection", False),
        ("sec_sql_injection", True),
        ("clean_rename_and_docs", False),
        ("clean_rename_and_docs", True),
    }
    sql = [r for r in records if r["scenario"] == "sec_sql_injection"]
    assert all(r["bugs_found"] == ["SELECT id, name FROM users WHERE name"] for r in sql)
    clean = [r for r in records if r["scenario"] == "clean_rename_and_docs"]
    assert all(r["false_positives"] == 1 for r in clean)
    assert all(r["tokens"] == 33 for r in records)  # 3 agents x 11
    assert all(r["latency_s"] >= 0 for r in records)
    # RAG runs record what was retrieved; non-RAG runs record nothing
    assert all(r["retrieved"] for r in sql if r["rag"])
    assert all(r["retrieved"] == [] for r in records if not r["rag"])


def test_a_failing_run_is_recorded_and_does_not_stop_the_rest(tmp_path: Path) -> None:
    def explode(system: str, user: str) -> AgentOutput:
        raise RuntimeError("rate limited")

    scenarios = [s for s in ALL_SCENARIOS if s.id == "sec_sql_injection"]
    settings = Settings(chroma_dir=tmp_path / "chroma", google_api_key="test-key")
    records = run_all(
        scenarios, settings, FakeChatModel(explode), FakeEmbeddings(), tmp_path / "repos"
    )
    assert len(records) == 2
    assert all(not r["ok"] and "rate limited" in r["error"] for r in records)


def test_summary_and_saved_files(tmp_path: Path) -> None:
    scenarios = [s for s in ALL_SCENARIOS if s.id in {"sec_sql_injection", "clean_rename_and_docs"}]
    settings = Settings(chroma_dir=tmp_path / "chroma", google_api_key="test-key")
    records = run_all(scenarios, settings, sql_aware_model(), FakeEmbeddings(), tmp_path / "repos")
    meta = {"timestamp": "2026-01-01T00-00-00Z", "llm_model": "fake", "embedding_model": "fake"}

    text = summarize(records, meta)
    assert "Planted bugs found (recall) | 1/1 (100%) | 1/1 (100%)" in text
    assert "False positives on clean changes | 1 | 1" in text
    assert "Do not conclude that RAG helps" in text

    json_path, md_path = save(records, meta, tmp_path / "out")
    saved = json.loads(json_path.read_text(encoding="utf-8"))
    assert len(saved["records"]) == 4
    assert saved["records"][0]["findings"] is not None  # raw findings are kept
    assert md_path.read_text(encoding="utf-8") == text


def test_summary_only_compares_scenarios_where_both_modes_finished() -> None:
    ok = {
        "needs_context": False,
        "ok": True,
        "error": None,
        "tokens": 1,
        "latency_s": 1.0,
        "bugs_expected": 1,
        "bugs_found": ["m"],
        "bugs_missed": [],
        "false_positives": 0,
        "kind": "security",
    }
    records = [
        {**ok, "scenario": "a", "rag": False},
        {**ok, "scenario": "a", "rag": True},
        {**ok, "scenario": "b", "rag": False},  # RAG run for b failed
        {"scenario": "b", "rag": True, "ok": False, "error": "boom", "kind": "security"},
    ]
    meta = {"timestamp": "t", "llm_model": "m", "embedding_model": "e"}
    text = summarize(records, meta)
    assert "Scenarios compared: 1 of 2" in text
    assert "boom" in text
