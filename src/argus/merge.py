"""Merges the three agents' findings into one report. Plain code, no LLM involved."""

from __future__ import annotations

from difflib import SequenceMatcher

from argus.models import Finding, Report, Severity, Snippet

SEVERITY_RANK = {Severity.CRITICAL: 3, Severity.HIGH: 2, Severity.MEDIUM: 1, Severity.LOW: 0}
# Risk score: each merged finding adds points by severity; the total is capped at 100.
# The weights are a judgment call: one critical (40) outweighs four mediums (32).
SEVERITY_WEIGHTS = {Severity.CRITICAL: 40, Severity.HIGH: 20, Severity.MEDIUM: 8, Severity.LOW: 2}
MAX_RISK_SCORE = 100
SIMILARITY_THRESHOLD = 0.6  # description similarity (0 to 1) above which two texts match
LINE_TOLERANCE = 2  # findings this many lines apart count as the same spot


def similar(a: str, b: str) -> bool:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() >= SIMILARITY_THRESHOLD


def is_duplicate(a: Finding, b: Finding) -> bool:
    """Do two findings describe the same problem?

    - Different files: never.
    - Both point at (nearly) the same line, or both have no line: duplicate if they
      have the same category or similar descriptions.
    - Only one has a line number: duplicate only if the descriptions are similar.
    - Lines far apart: different problems, even if worded alike.
    """
    if a.file != b.file:
        return False
    if a.line is not None and b.line is not None:
        if abs(a.line - b.line) > LINE_TOLERANCE:
            return False
        return a.category == b.category or similar(a.description, b.description)
    if a.line is None and b.line is None:
        return a.category == b.category or similar(a.description, b.description)
    return similar(a.description, b.description)


def merge_findings(findings: list[Finding]) -> list[Finding]:
    """Remove duplicates, keeping the most severe version, and sort the result."""
    kept: list[Finding] = []
    # Most severe first, so when two findings are duplicates the worse one survives.
    for finding in sorted(findings, key=lambda f: -SEVERITY_RANK[f.severity]):
        if not any(is_duplicate(finding, other) for other in kept):
            kept.append(finding)
    kept.sort(key=lambda f: (-SEVERITY_RANK[f.severity], f.file, f.line if f.line else 10**9))
    return kept


def risk_score(merged: list[Finding]) -> int:
    """Sum of severity weights, capped at 100.

    Call this with the MERGED findings: duplicates were already removed by
    merge_findings(), so the same problem reported by two agents counts once.
    """
    return min(MAX_RISK_SCORE, sum(SEVERITY_WEIGHTS[f.severity] for f in merged))


def risk_level(merged: list[Finding]) -> str:
    """The worst severity present (the score alone can hide one critical finding)."""
    if not merged:
        return "none"
    return max((f.severity for f in merged), key=lambda s: SEVERITY_RANK[s]).value


def build_report(
    findings: list[Finding], snippets: list[Snippet] | None, tokens: int = 0
) -> Report:
    merged = merge_findings(findings)
    counts = {s.value: 0 for s in Severity}
    for f in merged:
        counts[f.severity.value] += 1
    files = sorted({f.file for f in merged})

    if merged:
        by_severity = ", ".join(f"{n} {name}" for name, n in counts.items() if n)
        summary = (
            f"{len(merged)} finding(s) ({by_severity}) in {len(files)} file(s). "
            f"Risk: {risk_level(merged)} ({risk_score(merged)}/100)."
        )
    else:
        summary = "No issues found by the security, correctness and performance reviewers."
    return Report(
        summary=summary,
        findings=merged,
        severity_counts=counts,
        files_with_findings=files,
        retrieved_context=snippets or [],
        rag_enabled=snippets is not None,
        risk_score=risk_score(merged),
        risk_level=risk_level(merged),
        tokens_used=tokens,
    )
