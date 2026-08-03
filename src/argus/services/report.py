"""Renders a :class:`FinalReview` as Markdown or a Rich console report.

Kept separate from the CLI so the API can reuse the Markdown renderer (e.g.
for a future "post as PR comment" integration) without importing Typer.
"""

from __future__ import annotations

from io import StringIO

from rich.console import Console
from rich.markdown import Markdown

from argus.models.review import FinalReview, Severity

_SEVERITY_EMOJI = {
    Severity.CRITICAL: "🔴",
    Severity.HIGH: "🟠",
    Severity.MEDIUM: "🟡",
    Severity.LOW: "🟢",
}


def render_markdown(review: FinalReview) -> str:
    lines: list[str] = []
    lines.append("# Argus Review Report\n")
    lines.append(f"**Recommendation:** `{review.recommendation.value}`  ")
    lines.append(f"**Confidence:** {review.confidence_score:.0%}  ")
    lines.append(
        f"**Overall risk:** {_SEVERITY_EMOJI[review.risk_assessment.overall_risk]} "
        f"{review.risk_assessment.overall_risk.value} ({review.risk_assessment.risk_score:.0f}/100)\n"
    )
    lines.append("## Summary\n")
    lines.append(review.summary + "\n")

    lines.append("## Risk assessment\n")
    lines.append(review.risk_assessment.rationale + "\n")
    if review.files_requiring_manual_review:
        lines.append("**Files requiring manual review:**")
        for path in review.files_requiring_manual_review:
            lines.append(f"- `{path}`")
        lines.append("")

    lines.append("## Security\n")
    lines.append(review.security.summary + "\n")
    for finding in review.security.vulnerabilities:
        lines.append(
            f"- {_SEVERITY_EMOJI[finding.severity]} **{finding.title}** "
            f"(`{finding.file_path}`{f':{finding.line_start}' if finding.line_start else ''})"
            f"{f' — {finding.cwe_id}' if finding.cwe_id else ''}\n"
            f"  - {finding.description}\n"
            f"  - Fix: {finding.suggested_fix}"
        )
    lines.append("")

    lines.append("## Performance\n")
    lines.append(review.performance.summary + "\n")
    for issue in review.performance.bottlenecks:
        complexity = f" ({issue.complexity_estimate})" if issue.complexity_estimate else ""
        lines.append(f"- **{issue.title}**{complexity} — `{issue.file_path}`\n  - {issue.description}")
    lines.append("")

    lines.append("## Architecture\n")
    lines.append(review.architecture.summary + "\n")
    lines.append(f"- Coupling: {review.architecture.coupling_notes}")
    lines.append(f"- Cohesion: {review.architecture.cohesion_notes}")
    for concern in review.architecture.solid_violations:
        principle = f" ({concern.principle})" if concern.principle else ""
        lines.append(f"- {_SEVERITY_EMOJI[concern.severity]} **{concern.title}**{principle} — `{concern.file_path}`")
    lines.append("")

    lines.append("## Code quality\n")
    lines.append(f"Maintainability: {review.quality.maintainability_score:.1f}/10\n")
    lines.append(review.quality.summary + "\n")
    for issue in review.quality.issues:
        lines.append(f"- {_SEVERITY_EMOJI[issue.severity]} [{issue.category}] **{issue.title}** — `{issue.file_path}`")
    lines.append("")

    lines.append("## Testing\n")
    lines.append(review.testing.summary + "\n")
    for missing in review.testing.missing_tests:
        target = f"{missing.file_path}::{missing.function_name}" if missing.function_name else missing.file_path
        lines.append(f"- `{target}` — {missing.reason} (risk: {missing.risk_if_untested})")
    lines.append("")

    if review.suggested_improvements:
        lines.append("## Suggested improvements\n")
        for item in review.suggested_improvements:
            lines.append(f"- {item}")
        lines.append("")

    return "\n".join(lines)


def render_console(review: FinalReview) -> str:
    """Render a colorized console-friendly report; returns the captured text."""
    buffer = StringIO()
    console = Console(file=buffer, width=100)
    console.print(Markdown(render_markdown(review)))
    return buffer.getvalue()
