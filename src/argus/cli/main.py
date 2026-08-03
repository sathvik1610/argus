"""Argus CLI: review, index, graph, config, and doctor commands."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from argus.config import LLMProvider, get_settings
from argus.graph.workflow import build_graph_topology
from argus.retrieval.indexer import index_repository
from argus.retrieval.vector_store import RepositoryIndex
from argus.services.logging import configure_logging
from argus.services.report import render_console, render_markdown
from argus.services.review_service import run_review
from argus.tools.repository import RepositoryLoader

app = typer.Typer(help="Argus: AI-powered pull request review, built on LangGraph.")
console = Console()


@app.command()
def review(
    repo_path: str = typer.Argument(..., help="Path to a local git repository"),
    base: str = typer.Option(..., "--base", "-b", help="Base ref/branch to diff against"),
    head: str = typer.Option("HEAD", "--head", help="Head ref/branch (defaults to HEAD)"),
    output_format: str = typer.Option("console", "--format", "-f", help="console | markdown | json"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write report to a file"),
) -> None:
    """Run the full multi-agent review of a diff between two refs."""
    settings = get_settings()
    configure_logging(settings.log_level)

    with console.status(f"Reviewing {repo_path} ({base}..{head})..."):
        state = run_review(repo_path, base, head, settings)

    final = state["final_review"]
    if output_format == "json":
        text = final.model_dump_json(indent=2)
    elif output_format == "markdown":
        text = render_markdown(final)
    elif output_format == "console":
        text = render_console(final)
    else:
        raise typer.BadParameter(f"unknown format: {output_format}")

    if output:
        output.write_text(text, encoding="utf-8")
        console.print(f"[green]Report written to {output}[/green]")
    else:
        console.print(text, end="" if output_format == "console" else "\n")

    if final.recommendation.value == "block":
        raise typer.Exit(code=1)


@app.command()
def index(
    repo_path: str = typer.Argument(..., help="Path to a local git repository"),
    ref: str = typer.Option("HEAD", "--ref", help="Ref to index"),
) -> None:
    """Build (or refresh) the semantic index for a repository without running a review."""
    settings = get_settings()
    configure_logging(settings.log_level)

    loader = RepositoryLoader(repo_path)
    vector_index = RepositoryIndex(settings, repo_path)
    with console.status(f"Indexing {repo_path} @ {ref}..."):
        result = index_repository(loader, vector_index, ref=ref)

    console.print(
        f"Scanned [bold]{result.files_scanned}[/bold] files, "
        f"indexed [bold]{result.files_indexed}[/bold], "
        f"embedded [bold]{result.chunks_indexed}[/bold] chunks."
    )


@app.command()
def graph(
    output: Path | None = typer.Option(None, "--output", "-o", help="Write Mermaid diagram to a file"),
) -> None:
    """Print the review workflow's graph structure as a Mermaid diagram."""
    compiled = build_graph_topology()
    mermaid = compiled.get_graph().draw_mermaid()
    if output:
        output.write_text(mermaid, encoding="utf-8")
        console.print(f"[green]Wrote graph diagram to {output}[/green]")
    else:
        console.print(mermaid)


@app.command()
def config() -> None:
    """Show the currently resolved configuration."""
    settings = get_settings()
    table = Table(title="Argus configuration")
    table.add_column("Setting")
    table.add_column("Value")

    def _mask(value: str | None) -> str:
        if not value:
            return "[red]not set[/red]"
        return f"{'*' * max(len(value) - 4, 0)}{value[-4:]}"

    table.add_row("LLM provider", settings.llm_provider.value)
    table.add_row("LLM model", settings.resolved_model())
    table.add_row("Embedding provider", settings.resolved_embedding_provider().value)
    table.add_row("Google API key", _mask(settings.google_api_key))
    table.add_row("OpenAI API key", _mask(settings.openai_api_key))
    table.add_row("Anthropic API key", _mask(settings.anthropic_api_key))
    table.add_row("Ollama base URL", settings.ollama_base_url)
    table.add_row("Chroma dir", str(settings.chroma_dir))
    table.add_row("Max files per review", str(settings.max_files_per_review))
    table.add_row("Retrieval top-k", str(settings.retrieval_top_k))
    table.add_row("Max context expansion rounds", str(settings.max_context_expansion_rounds))
    console.print(table)


@app.command()
def doctor() -> None:
    """Check that Argus is correctly configured to run a review."""
    settings = get_settings()
    checks: list[tuple[str, bool, str]] = []

    checks.append(("Python >= 3.12", sys.version_info >= (3, 12), sys.version.split()[0]))
    checks.append(("git executable on PATH", shutil.which("git") is not None, shutil.which("git") or "not found"))

    provider_key_present = {
        LLMProvider.GOOGLE: bool(settings.google_api_key),
        LLMProvider.OPENAI: bool(settings.openai_api_key),
        LLMProvider.ANTHROPIC: bool(settings.anthropic_api_key),
        LLMProvider.OLLAMA: True,
    }[settings.llm_provider]
    checks.append(
        (
            f"API key set for provider ({settings.llm_provider.value})",
            provider_key_present,
            "configured" if provider_key_present else "missing - set the provider's API key env var",
        )
    )

    try:
        settings.chroma_dir.mkdir(parents=True, exist_ok=True)
        writable = True
    except OSError:
        writable = False
    checks.append(("Chroma directory is writable", writable, str(settings.chroma_dir)))

    table = Table(title="Argus doctor")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Detail")
    all_ok = True
    for name, ok, detail in checks:
        all_ok &= ok
        table.add_row(name, "[green]OK[/green]" if ok else "[red]FAIL[/red]", detail)
    console.print(table)

    if not all_ok:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
