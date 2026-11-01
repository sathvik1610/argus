from __future__ import annotations

from argus.merge import build_report, is_duplicate, merge_findings
from argus.models import Category, Finding, Severity, Snippet


def f(
    file: str = "a.py",
    line: int | None = 10,
    category: Category = Category.SECURITY,
    severity: Severity = Severity.MEDIUM,
    description: str = "something is wrong",
) -> Finding:
    return Finding(
        file=file,
        line=line,
        category=category,
        severity=severity,
        description=description,
        suggested_fix="fix",
    )


def test_same_file_same_line_same_category_is_duplicate() -> None:
    assert is_duplicate(f(description="alpha"), f(description="completely different"))


def test_same_spot_different_category_needs_similar_text() -> None:
    a = f(category=Category.SECURITY, description="User input is concatenated into the SQL query")
    b = f(category=Category.CORRECTNESS, description="User input is concatenated into SQL query")
    c = f(category=Category.CORRECTNESS, description="Off by one error in the loop bound")
    assert is_duplicate(a, b)
    assert not is_duplicate(a, c)


def test_lines_close_together_count_as_same_spot() -> None:
    assert is_duplicate(f(line=10), f(line=12))
    assert not is_duplicate(f(line=10), f(line=40))


def test_different_files_are_never_duplicates() -> None:
    assert not is_duplicate(f(file="a.py"), f(file="b.py"))


def test_missing_line_only_matches_on_similar_text() -> None:
    same = "The password is stored in plain text"
    assert is_duplicate(f(line=None, description=same), f(line=10, description=same))
    assert not is_duplicate(f(line=None, description=same), f(line=10, description="unrelated"))


def test_far_apart_lines_stay_separate_even_with_same_text() -> None:
    same = "The password is stored in plain text"
    assert not is_duplicate(f(line=5, description=same), f(line=80, description=same))


def test_merge_keeps_the_most_severe_duplicate() -> None:
    low = f(severity=Severity.LOW, description="x")
    high = f(severity=Severity.HIGH, description="y")
    merged = merge_findings([low, high])
    assert [m.severity for m in merged] == [Severity.HIGH]


def test_merge_sorts_by_severity_then_file_then_line() -> None:
    findings = [
        f(file="b.py", line=1, severity=Severity.LOW, description="unused variable left behind"),
        f(file="a.py", line=50, severity=Severity.HIGH, description="sql built from user input"),
        f(
            file="a.py",
            line=5,
            severity=Severity.HIGH,
            category=Category.PERFORMANCE,
            description="nested loop makes this quadratic",
        ),
        f(
            file="a.py",
            line=None,
            severity=Severity.CRITICAL,
            category=Category.CORRECTNESS,
            description="missing authorization check on delete",
        ),
    ]
    merged = merge_findings(findings)
    assert [(m.file, m.line) for m in merged] == [
        ("a.py", None),
        ("a.py", 5),
        ("a.py", 50),
        ("b.py", 1),
    ]


def test_report_counts_and_summary() -> None:
    report = build_report(
        [f(severity=Severity.HIGH), f(file="b.py", severity=Severity.LOW)], snippets=None, tokens=7
    )
    assert report.severity_counts == {"low": 1, "medium": 0, "high": 1, "critical": 0}
    assert report.files_with_findings == ["a.py", "b.py"]
    assert report.rag_enabled is False
    assert report.tokens_used == 7
    assert "2 finding(s)" in report.summary


def test_empty_report() -> None:
    report = build_report([], snippets=[], tokens=0)
    assert report.findings == []
    assert report.rag_enabled is True
    assert "No issues" in report.summary


def test_report_carries_retrieved_context() -> None:
    snippet = Snippet(file="w.py", start_line=1, end_line=3, name="withdraw", code="x")
    report = build_report([], snippets=[snippet])
    assert report.retrieved_context == [snippet]


def test_risk_score_uses_documented_weights() -> None:
    from argus.merge import risk_score

    findings = [
        f(line=1, severity=Severity.CRITICAL, description="a"),
        f(line=50, severity=Severity.HIGH, description="b"),
        f(line=90, severity=Severity.MEDIUM, description="c"),
        f(line=130, severity=Severity.LOW, description="d"),
    ]
    assert risk_score(findings) == 40 + 20 + 8 + 2


def test_risk_score_is_capped_at_100() -> None:
    from argus.merge import risk_score

    findings = [f(line=i * 10, severity=Severity.CRITICAL, description=f"d{i}") for i in range(5)]
    assert risk_score(findings) == 100


def test_duplicates_do_not_inflate_the_risk_score() -> None:
    from argus.merge import risk_score

    # The same problem reported by two agents (same file and line, similar text).
    security = f(
        category=Category.SECURITY, severity=Severity.HIGH, description="sql injection here"
    )
    correctness = f(
        category=Category.CORRECTNESS, severity=Severity.HIGH, description="sql injection here"
    )
    one = build_report([security], None)
    two = build_report([security, correctness], None)
    assert one.risk_score == two.risk_score == 20
    assert risk_score([security, correctness]) == 40  # raw, un-merged list WOULD double count


def test_risk_level_is_the_worst_severity() -> None:
    from argus.merge import risk_level

    assert risk_level([]) == "none"
    mixed = [
        f(line=1, severity=Severity.LOW, description="a"),
        f(line=99, severity=Severity.CRITICAL, description="b"),
    ]
    assert risk_level(mixed) == "critical"
    many_lows = [f(line=i * 20, severity=Severity.LOW, description=f"x{i}") for i in range(10)]
    assert risk_level(many_lows) == "low"  # 20 points, but still only low severity
