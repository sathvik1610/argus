"""Command line: python -m argus <repo> --base <ref> [--head <ref>]"""

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
    args = parser.parse_args()

    try:
        result = review_repo(args.repo, args.base, args.head)
    except (ConfigError, RepoError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if not result.findings:
        print("No findings.")
    for f in result.findings:
        where = f"{f.file}:{f.line}" if f.line else f.file
        print(
            f"[{f.severity.value}] ({f.category.value}) {where}\n  {f.description}\n  fix: {f.suggested_fix}\n"
        )
    print(f"tokens used: {result.tokens}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
