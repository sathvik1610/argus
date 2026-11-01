"""Decides which repository files to index, and splits them into chunks.

Chunking is deliberately simple:
- Python files are split at function and method boundaries using the standard `ast` module.
- Every other source file is split into overlapping windows of lines.
Each chunk remembers its file and line range so retrieved code can be cited.
"""

from __future__ import annotations

import ast
from pathlib import PurePosixPath

from argus.models import Snippet

SOURCE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rb", ".php",
    ".c", ".h", ".cpp", ".hpp", ".cs", ".rs", ".kt", ".swift",
}  # fmt: skip

# Folders that hold dependencies, build output or tool caches, never review targets.
SKIP_DIRS = {
    "node_modules", ".venv", "venv", "env", "site-packages", "dist", "build", "target",
    "vendor", "__pycache__", ".git", ".tox", ".mypy_cache", ".pytest_cache", "generated",
}  # fmt: skip

SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".jks")
SECRET_NAME_PARTS = ("secret", "credential", "id_rsa", "id_ed25519", "password")

MAX_FILE_BYTES = 200_000
MAX_FUNCTION_LINES = 80  # longer functions are split into windows
WINDOW_LINES = 50
WINDOW_OVERLAP = 10


def should_index_path(path: str) -> bool:
    """Cheap check using only the file path."""
    p = PurePosixPath(path)
    if p.suffix.lower() not in SOURCE_EXTENSIONS:
        return False
    if any(part in SKIP_DIRS for part in p.parts[:-1]):
        return False
    name = p.name.lower()
    if name.startswith(".env") or name.endswith(SECRET_SUFFIXES):
        return False
    if any(part in name for part in SECRET_NAME_PARTS):
        return False
    # minified or machine-generated code
    return not (".min." in name or "_pb2" in name or ".generated." in name)


def should_index_text(text: str) -> bool:
    """Check on the content: skip huge files and anything that looks binary."""
    return len(text) <= MAX_FILE_BYTES and "\x00" not in text


def chunk_file(path: str, text: str) -> list[Snippet]:
    if path.endswith(".py"):
        try:
            return _chunk_python(path, text)
        except SyntaxError:
            pass  # broken Python: fall back to plain windows
    return _windows(path, text.splitlines(), 1, None)


def _snippet(path: str, lines: list[str], start: int, end: int, name: str | None) -> Snippet | None:
    code = "\n".join(lines[start - 1 : end])
    if not code.strip():
        return None
    return Snippet(file=path, start_line=start, end_line=end, name=name, code=code)


def _windows(path: str, lines: list[str], start: int, name: str | None) -> list[Snippet]:
    """Split lines (which begin at file line `start`) into overlapping windows."""
    out: list[Snippet] = []
    offset = 0
    while offset < len(lines):
        part = lines[offset : offset + WINDOW_LINES]
        code = "\n".join(part)
        if code.strip():
            first = start + offset
            out.append(
                Snippet(
                    file=path,
                    start_line=first,
                    end_line=first + len(part) - 1,
                    name=name,
                    code=code,
                )
            )
        if offset + WINDOW_LINES >= len(lines):
            break
        offset += WINDOW_LINES - WINDOW_OVERLAP
    return out


def _chunk_python(path: str, text: str) -> list[Snippet]:
    tree = ast.parse(text)
    lines = text.splitlines()
    chunks: list[Snippet] = []

    def add_function(node: ast.FunctionDef | ast.AsyncFunctionDef, name: str) -> None:
        # Decorators belong to the function even though they sit above `def`.
        start = min([node.lineno, *(d.lineno for d in node.decorator_list)])
        end = node.end_lineno or node.lineno
        if end - start + 1 > MAX_FUNCTION_LINES:
            chunks.extend(_windows(path, lines[start - 1 : end], start, name))
        elif (s := _snippet(path, lines, start, end, name)) is not None:
            chunks.append(s)

    run_start: int | None = None  # start of a run of top-level non-function statements
    run_end = 0

    def flush_run() -> None:
        nonlocal run_start
        if run_start is not None and (s := _snippet(path, lines, run_start, run_end, "<module>")):
            chunks.append(s)
        run_start = None

    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            flush_run()
            add_function(node, node.name)
        elif isinstance(node, ast.ClassDef):
            flush_run()
            methods = [
                n for n in node.body if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)
            ]
            if not methods:
                if s := _snippet(
                    path, lines, node.lineno, node.end_lineno or node.lineno, node.name
                ):
                    chunks.append(s)
                continue
            # the class header: docstring and attributes before the first method
            first = min([methods[0].lineno, *(d.lineno for d in methods[0].decorator_list)])
            if first - 1 > node.lineno and (
                s := _snippet(path, lines, node.lineno, first - 1, node.name)
            ):
                chunks.append(s)
            for method in methods:
                add_function(method, f"{node.name}.{method.name}")
        else:
            if run_start is None:
                run_start = node.lineno
            run_end = node.end_lineno or node.lineno
    flush_run()
    return chunks
