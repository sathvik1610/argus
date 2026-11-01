"""Command line: python -m argus <repo> --base <ref> [--head <ref>] [--no-rag] [--json]"""

from __future__ import annotations

import argparse
import sys

from argus.config import ConfigError
from argus.git_diff import RepoError
from argus.service import review_repo


def main() -> int:
    parser = argparse.ArgumentParser(prog="argus", description="Review a git diff with LLM agents.")
    parser.add_argument("repo", help="path to a local git repository")
    parser.add_argument("--base", required=True, help="base branch or commit")
    parser.add_argument("--head", default="HEAD", help="head branch or commit (default HEAD)")
    parser.add_argument("--no-rag", action="store_true", help="review the diff only, no retrieval")
    parser.add_argument("--json", action="store_true", help="print the full report as JSON")
    args = parser.parse_args()

    try:
        report = review_repo(args.repo, args.base, args.head, rag=not args.no_rag)
    except (ConfigError, RepoError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(report.model_dump_json(indent=2))
        return 0

    print(report.summary)
    print(f"risk score: {report.risk_score}/100 ({report.risk_level})")
    for f in report.findings:
        where = f"{f.file}:{f.line}" if f.line else f.file
        print(f"\n[{f.severity.value}] ({f.category.value}) {where}")
        print(f"  {f.description}\n  fix: {f.suggested_fix}")
    if report.retrieved_context:
        print("\nContext retrieved:")
        for s in report.retrieved_context:
            print(f"  {s.file}:{s.start_line}-{s.end_line} {s.name or ''}")
    print(f"\ntokens used: {report.tokens_used}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
