"""Data types for evaluation scenarios, plus code shared by all of them."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExpectedBug:
    """A bug planted on purpose. A finding counts as catching it when it is in the
    same file AND either points near the marker line or mentions one of the keywords."""

    file: str
    marker: str  # a piece of the buggy line; we look it up to get the line number
    keywords: tuple[str, ...]  # lowercase phrases a correct finding would likely use


@dataclass(frozen=True)
class Scenario:
    id: str
    kind: str  # security | correctness | performance | clean
    description: str
    base_files: dict[str, str]  # the repository before the PR
    pr_files: dict[str, str]  # files the PR adds or changes (full new content)
    expected: tuple[ExpectedBug, ...] = ()
    needs_context: bool = False  # True if spotting the bug needs code outside the changed file


# Unrelated code added to every repo, so retrieval has distractors to ignore.
FILLER_FILES = {
    "text_utils.py": (
        "def slugify(text):\n"
        '    return "-".join(text.lower().split())\n\n\n'
        "def truncate(text, limit):\n"
        "    return text if len(text) <= limit else text[: limit - 3] + '...'\n"
    ),
    "dates.py": (
        "from datetime import date\n\n\n"
        "def is_weekend(day):\n"
        "    return day.weekday() >= 5\n\n\n"
        "def days_until(target):\n"
        "    return (target - date.today()).days\n"
    ),
    "colors.py": (
        "PALETTE = {'red': '#ff0000', 'green': '#00ff00', 'blue': '#0000ff'}\n\n\n"
        "def hex_for(name):\n"
        "    return PALETTE[name]\n"
    ),
}
