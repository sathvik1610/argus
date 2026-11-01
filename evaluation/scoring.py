"""Decides which planted bugs a review caught, and which findings were false alarms.

The matching is deliberately simple (same file, and near the buggy line or mentions a
keyword). It is approximate, which is why every run also saves the raw findings: read
them yourself before trusting a number.
"""

from __future__ import annotations

from dataclasses import dataclass

from argus.models import Finding
from evaluation.scenario import ExpectedBug, Scenario

LINE_TOLERANCE = 2  # a finding this close to the buggy line counts as pointing at it


@dataclass
class Score:
    found: list[str]  # markers of planted bugs the review caught
    missed: list[str]  # markers of planted bugs it did not catch
    false_positives: list[Finding]  # findings that match no planted bug


def marker_line(scenario: Scenario, bug: ExpectedBug) -> int:
    """Line number (1-based) of the buggy line in the PR's version of the file."""
    for number, line in enumerate(scenario.pr_files[bug.file].splitlines(), start=1):
        if bug.marker in line:
            return number
    raise ValueError(f"marker {bug.marker!r} not found in {bug.file} of {scenario.id}")


def matches(finding: Finding, bug: ExpectedBug, bug_line: int) -> bool:
    if finding.file != bug.file:
        return False
    text = f"{finding.description} {finding.suggested_fix}".lower()
    near = finding.line is not None and abs(finding.line - bug_line) <= LINE_TOLERANCE
    return near or any(keyword in text for keyword in bug.keywords)


def score_findings(scenario: Scenario, findings: list[Finding]) -> Score:
    lines = {bug.marker: marker_line(scenario, bug) for bug in scenario.expected}
    found = [
        bug.marker
        for bug in scenario.expected
        if any(matches(f, bug, lines[bug.marker]) for f in findings)
    ]
    missed = [bug.marker for bug in scenario.expected if bug.marker not in found]
    false_positives = [
        f
        for f in findings
        if not any(matches(f, bug, lines[bug.marker]) for bug in scenario.expected)
    ]
    return Score(found=found, missed=missed, false_positives=false_positives)
