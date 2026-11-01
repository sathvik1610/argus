"""Runs every scenario with and without RAG and saves the results.

    uv run python -m evaluation.run              # needs GOOGLE_API_KEY in .env
    uv run python -m evaluation.run --only sec_sql_injection --pause 5

Each scenario becomes a tiny git repo (one commit for the base, one for the PR). The
same repo is reviewed twice: first with only the diff, then with the diff plus
retrieved repository code. Nothing here is simulated: results come from whatever
model you configured.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from langchain_core.embeddings import Embeddings

from argus.config import ConfigError, Settings
from argus.service import review_repo
from evaluation.scenario import FILLER_FILES, Scenario
from evaluation.scenarios import ALL_SCENARIOS
from evaluation.scoring import score_findings

DEFAULT_OUT_DIR = Path(__file__).parent / "results"


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=eval", "-c", "user.email=eval@example.com", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def write_files(repo: Path, files: dict[str, str]) -> None:
    for name, content in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def build_repo(scenario: Scenario, dest: Path) -> Path:
    """Commit 1 = base repository, commit 2 = the PR. Review it with HEAD~1..HEAD."""
    dest.mkdir(parents=True, exist_ok=True)
    git(dest, "init", "-q")
    write_files(dest, {**FILLER_FILES, **scenario.base_files})
    git(dest, "add", ".")
    git(dest, "commit", "-q", "-m", "base")
    write_files(dest, scenario.pr_files)
    git(dest, "add", ".")
    git(dest, "commit", "-q", "-m", scenario.description)
    return dest


def run_one(
    scenario: Scenario,
    repo: Path,
    rag: bool,
    settings: Settings,
    model: Any,
    embeddings: Embeddings | None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "scenario": scenario.id,
        "kind": scenario.kind,
        "needs_context": scenario.needs_context,
        "rag": rag,
        "ok": True,
        "error": None,
    }
    start = time.perf_counter()
    try:
        report = review_repo(
            str(repo),
            "HEAD~1",
            "HEAD",
            rag=rag,
            settings=settings,
            model=model,
            embeddings=embeddings,
        )
    except Exception as exc:  # one failed run (rate limit, bad output) must not stop the rest
        record.update(ok=False, error=f"{type(exc).__name__}: {exc}")
        return record
    latency = time.perf_counter() - start

    score = score_findings(scenario, report.findings)
    record.update(
        latency_s=round(latency, 2),  # with RAG this includes building the index
        tokens=report.tokens_used,
        risk_score=report.risk_score,
        findings=[f.model_dump(mode="json") for f in report.findings],
        retrieved=[f"{s.file}:{s.start_line}-{s.end_line}" for s in report.retrieved_context],
        bugs_expected=len(scenario.expected),
        bugs_found=score.found,
        bugs_missed=score.missed,
        false_positives=len(score.false_positives),
    )
    return record


def run_all(
    scenarios: list[Scenario],
    settings: Settings,
    model: Any,
    embeddings: Embeddings | None,
    work_dir: Path,
    pause: float = 0.0,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for scenario in scenarios:
        repo = build_repo(scenario, work_dir / scenario.id)
        for rag in (False, True):
            label = "RAG   " if rag else "no RAG"
            print(f"[{scenario.id}] {label} ...", end=" ", flush=True)
            record = run_one(scenario, repo, rag, settings, model, embeddings)
            records.append(record)
            if record["ok"]:
                print(
                    f"found {len(record['bugs_found'])}/{record['bugs_expected']}, "
                    f"{record['false_positives']} false positive(s), {record['latency_s']}s"
                )
            else:
                print(f"ERROR {record['error']}")
            if pause:
                time.sleep(pause)  # helps stay under free-tier rate limits
    return records


def _pct(part: int, whole: int) -> str:
    return f"{part}/{whole} ({part / whole:.0%})" if whole else "n/a"


def _mode_stats(records: list[dict[str, Any]]) -> dict[str, Any]:
    expected = sum(r["bugs_expected"] for r in records)
    found = sum(len(r["bugs_found"]) for r in records)
    ctx = [r for r in records if r["needs_context"]]
    return {
        "recall": _pct(found, expected),
        "ctx_recall": _pct(
            sum(len(r["bugs_found"]) for r in ctx), sum(r["bugs_expected"] for r in ctx)
        ),
        "false_positives": sum(r["false_positives"] for r in records),
        "clean_false_positives": sum(r["false_positives"] for r in records if r["kind"] == "clean"),
        "tokens": sum(r["tokens"] for r in records),
        "latency": round(sum(r["latency_s"] for r in records) / len(records), 1),
    }


def summarize(records: list[dict[str, Any]], meta: dict[str, Any]) -> str:
    """A markdown summary. Only scenarios where BOTH modes finished are compared."""
    by_scenario: dict[str, dict[bool, dict[str, Any]]] = {}
    for r in records:
        by_scenario.setdefault(r["scenario"], {})[r["rag"]] = r
    pairs = {
        sid: modes
        for sid, modes in by_scenario.items()
        if modes.get(False, {}).get("ok") and modes.get(True, {}).get("ok")
    }
    errors = [r for r in records if not r["ok"]]

    lines = [
        "# Evaluation results",
        "",
        f"- Run at: {meta['timestamp']}",
        f"- Chat model: `{meta['llm_model']}`, embedding model: `{meta['embedding_model']}`",
        f"- Scenarios compared: {len(pairs)} of {len(by_scenario)} "
        f"({len(errors)} run(s) failed and were excluded)",
        "",
    ]
    if pairs:
        off = _mode_stats([m[False] for m in pairs.values()])
        on = _mode_stats([m[True] for m in pairs.values()])
        lines += [
            "| Metric | Diff only | Diff + RAG |",
            "|---|---|---|",
            f"| Planted bugs found (recall) | {off['recall']} | {on['recall']} |",
            f"| ...only bugs needing cross-file context | {off['ctx_recall']} | {on['ctx_recall']} |",
            f"| False positives (all scenarios) | {off['false_positives']} | {on['false_positives']} |",
            f"| False positives on clean changes | {off['clean_false_positives']} | {on['clean_false_positives']} |",
            f"| Total tokens | {off['tokens']} | {on['tokens']} |",
            f"| Mean latency per review (s) | {off['latency']} | {on['latency']} |",
            "",
            "## Per scenario",
            "",
            "| Scenario | Kind | Needs context | Found (diff) | Found (RAG) | FP (diff) | FP (RAG) |",
            "|---|---|---|---|---|---|---|",
        ]
        for sid, m in pairs.items():
            a, b = m[False], m[True]
            lines.append(
                f"| {sid} | {a['kind']} | {'yes' if a['needs_context'] else 'no'} | "
                f"{len(a['bugs_found'])}/{a['bugs_expected']} | {len(b['bugs_found'])}/{b['bugs_expected']} | "
                f"{a['false_positives']} | {b['false_positives']} |"
            )
        lines.append("")
    if errors:
        lines += ["## Failed runs", ""]
        lines += [f"- {r['scenario']} (RAG={r['rag']}): {r['error']}" for r in errors]
        lines.append("")
    lines += [
        "## How to read this",
        "",
        "- Small sample: a handful of scenarios, one run each. A language model is not fully "
        "repeatable, so a difference of one or two bugs can be noise.",
        "- The bugs and the clean changes were written by the project author, which can bias "
        "results. Treat this as a smoke test, not a benchmark.",
        "- A finding counts as catching a bug if it is in the right file and is near the buggy "
        "line or uses an expected keyword. This is approximate: check the raw findings in the "
        "JSON file.",
        "- Latency in RAG mode includes building the index (embedding the repository).",
        "- Do not conclude that RAG helps (or hurts) unless the table above shows it clearly.",
    ]
    return "\n".join(lines) + "\n"


def save(records: list[dict[str, Any]], meta: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = meta["timestamp"].replace(":", "-")
    json_path = out_dir / f"results-{stamp}.json"
    md_path = out_dir / f"summary-{stamp}.md"
    json_path.write_text(json.dumps({"meta": meta, "records": records}, indent=2), encoding="utf-8")
    md_path.write_text(summarize(records, meta), encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare reviews with and without RAG.")
    parser.add_argument("--only", nargs="*", help="run only these scenario ids")
    parser.add_argument("--pause", type=float, default=0.0, help="seconds to wait between runs")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_DIR, help="where to save results")
    args = parser.parse_args()

    scenarios = [s for s in ALL_SCENARIOS if not args.only or s.id in args.only]
    if not scenarios:
        print("no scenarios selected", file=sys.stderr)
        return 1

    from argus.llm import get_chat_model, get_embeddings

    with tempfile.TemporaryDirectory(prefix="argus-eval-") as tmp:
        work_dir = Path(tmp)
        settings = Settings(chroma_dir=work_dir / "chroma")
        try:
            model = get_chat_model(settings)
            embeddings = get_embeddings(settings)
        except ConfigError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        records = run_all(scenarios, settings, model, embeddings, work_dir / "repos", args.pause)

    meta = {
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ"),
        "llm_model": settings.llm_model,
        "embedding_model": settings.embedding_model,
    }
    json_path, md_path = save(records, meta, args.out)
    print(f"\nSaved raw results to {json_path}\nSaved summary to {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
