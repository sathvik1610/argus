"""Shared helpers for turning domain models into prompt text.

Every agent needs roughly the same view of "what changed" and "what related
code looks like" — centralizing the rendering keeps the five reviewer prompts
consistent and means a formatting fix only has to happen once.
"""

from __future__ import annotations

from argus.models.context import RetrievedContext
from argus.models.diff import PullRequestDiff

_MAX_DIFF_CHARS = 12_000
_MAX_CONTEXT_CHARS = 8_000


def render_diff(diff: PullRequestDiff) -> str:
    lines = [f"PR diff: {diff.base_ref[:8]}..{diff.head_ref[:8]}"]
    lines.append(
        f"{diff.total_files_changed} file(s) changed, "
        f"+{diff.total_additions}/-{diff.total_deletions} lines"
    )
    for file_diff in diff.files:
        lines.append(f"\n--- {file_diff.path} ({file_diff.change_type.value}) ---")
        if file_diff.is_binary:
            lines.append("[binary file]")
            continue
        for hunk in file_diff.hunks:
            lines.append(hunk.header)
            for line in hunk.lines:
                prefix = line.kind if line.kind != " " else " "
                lines.append(f"{prefix}{line.content}")
    rendered = "\n".join(lines)
    if len(rendered) > _MAX_DIFF_CHARS:
        rendered = rendered[:_MAX_DIFF_CHARS] + "\n... [diff truncated for length] ..."
    return rendered


def render_context(context: RetrievedContext) -> str:
    rendered = context.render()
    if len(rendered) > _MAX_CONTEXT_CHARS:
        rendered = rendered[:_MAX_CONTEXT_CHARS] + "\n... [context truncated for length] ..."
    return rendered or "(no additional repository context retrieved)"


def render_review_prompt(diff: PullRequestDiff, context: RetrievedContext) -> str:
    return (
        f"## Diff under review\n{render_diff(diff)}\n\n"
        f"## Related repository context (functions/classes near the change)\n"
        f"{render_context(context)}"
    )
