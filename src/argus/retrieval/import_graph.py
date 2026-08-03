"""Repo-wide import/dependency graph, used to rank which files matter for a review.

Only Python and JavaScript/TypeScript get real import resolution — they cover
the overwhelming majority of repos this project targets, and "resolve imports
against a symbol table" is a fundamentally per-language problem with limited
payoff from generalizing further. Unrecognized languages simply contribute no
edges: their files still get indexed and can still be pulled in by name/path
matching or the diff itself, they just don't benefit from centrality-based
ranking.
"""

from __future__ import annotations

import ast
import re
from pathlib import PurePosixPath

import networkx as nx

_JS_IMPORT_RE = re.compile(
    r"""(?:import\s+(?:[\w*${},\s]+\s+from\s+)?|export\s+(?:[\w*${},\s]+\s+from\s+)?|require\()\s*['"](?P<spec>\.{1,2}/[^'"]+)['"]"""
)

_JS_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")


def build_import_graph(file_contents: dict[str, str]) -> nx.DiGraph:
    """Build a directed graph with an edge importer -> imported for resolved imports.

    ``file_contents`` maps repo-relative POSIX paths to their source text. Every
    path becomes a node even if it has no resolvable edges, so callers can
    always look up centrality/degree for any file in the repo.
    """
    graph: nx.DiGraph = nx.DiGraph()
    graph.add_nodes_from(file_contents.keys())

    python_files = {p for p in file_contents if p.endswith((".py", ".pyi"))}
    module_index = _build_python_module_index(python_files)

    for path, source in file_contents.items():
        if path.endswith((".py", ".pyi")):
            targets = _python_imports(path, source, module_index)
        elif path.endswith(_JS_EXTENSIONS):
            targets = _js_imports(path, source, set(file_contents.keys()))
        else:
            targets = set()

        for target in targets:
            if target != path:
                graph.add_edge(path, target)

    return graph


def _build_python_module_index(python_files: set[str]) -> dict[str, str]:
    index: dict[str, str] = {}
    for path in python_files:
        pure = PurePosixPath(path)
        parts = list(pure.parts)
        if parts[-1] == "__init__.py":
            parts = parts[:-1]
        else:
            parts[-1] = pure.stem
        if not parts:
            continue
        index[".".join(parts)] = path
    return index


def _python_imports(path: str, source: str, module_index: dict[str, str]) -> set[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()

    current_parts = PurePosixPath(path).parts[:-1]  # containing package, as path parts
    targets: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in module_index:
                    targets.add(module_index[alias.name])
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                base_parts = list(
                    current_parts[: len(current_parts) - (node.level - 1)]
                    if node.level > 1
                    else current_parts
                )
                base = ".".join([*base_parts, node.module]) if node.module else ".".join(base_parts)
            else:
                base = node.module or ""

            if base in module_index:
                targets.add(module_index[base])
            for alias in node.names:
                candidate = f"{base}.{alias.name}" if base else alias.name
                if candidate in module_index:
                    targets.add(module_index[candidate])

    return targets


def _js_imports(path: str, source: str, repo_files: set[str]) -> set[str]:
    targets: set[str] = set()
    current_dir = PurePosixPath(path).parent

    for match in _JS_IMPORT_RE.finditer(source):
        spec = match.group("spec")
        resolved = _resolve_relative_js_import(current_dir, spec, repo_files)
        if resolved:
            targets.add(resolved)

    return targets


def _resolve_relative_js_import(
    current_dir: PurePosixPath, spec: str, repo_files: set[str]
) -> str | None:
    candidate_base = str((current_dir / spec).as_posix()) if spec != "." else str(current_dir)
    candidate_base = _normalize_posix_path(candidate_base)

    if candidate_base in repo_files:
        return candidate_base
    for ext in _JS_EXTENSIONS:
        if f"{candidate_base}{ext}" in repo_files:
            return f"{candidate_base}{ext}"
    for ext in _JS_EXTENSIONS:
        index_candidate = f"{candidate_base}/index{ext}"
        if index_candidate in repo_files:
            return index_candidate
    return None


def _normalize_posix_path(path: str) -> str:
    parts: list[str] = []
    for part in path.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)
