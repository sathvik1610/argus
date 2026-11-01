from __future__ import annotations

from argus.chunking import (
    MAX_FUNCTION_LINES,
    chunk_file,
    should_index_path,
    should_index_text,
)

PY_SOURCE = '''import os

LIMIT = 10


@decorator
def top(x):
    return x


class Account:
    """An account."""

    rate = 3

    def deposit(self, n):
        return n

    async def close(self):
        pass
'''


def names(chunks):  # type: ignore[no-untyped-def]
    return [c.name for c in chunks]


def test_python_is_split_at_function_and_method_boundaries() -> None:
    chunks = chunk_file("acct.py", PY_SOURCE)
    assert names(chunks) == ["<module>", "top", "Account", "Account.deposit", "Account.close"]


def test_function_chunk_includes_decorator_and_correct_lines() -> None:
    top = next(c for c in chunk_file("acct.py", PY_SOURCE) if c.name == "top")
    assert top.code.startswith("@decorator")
    assert (top.start_line, top.end_line) == (6, 8)


def test_module_chunk_keeps_constants() -> None:
    module = next(c for c in chunk_file("acct.py", PY_SOURCE) if c.name == "<module>")
    assert "LIMIT = 10" in module.code


def test_class_header_keeps_attributes() -> None:
    header = next(c for c in chunk_file("acct.py", PY_SOURCE) if c.name == "Account")
    assert "rate = 3" in header.code
    assert "def deposit" not in header.code


def test_very_long_function_is_split_into_windows() -> None:
    body = "\n".join(f"    x{i} = {i}" for i in range(MAX_FUNCTION_LINES + 40))
    chunks = chunk_file("big.py", f"def big():\n{body}\n")
    assert len(chunks) >= 2
    assert all(c.name == "big" for c in chunks)


def test_non_python_uses_overlapping_windows() -> None:
    text = "\n".join(f"line {i}" for i in range(120))
    chunks = chunk_file("app.js", text)
    assert len(chunks) == 3
    assert chunks[0].start_line == 1
    assert chunks[1].start_line < chunks[0].end_line  # windows overlap


def test_broken_python_falls_back_to_windows() -> None:
    chunks = chunk_file("bad.py", "def (((:\n  nope\n")
    assert len(chunks) == 1


def test_should_index_path_filters_junk() -> None:
    assert should_index_path("src/app.py")
    assert not should_index_path("node_modules/lib/index.js")
    assert not should_index_path(".venv/lib/site.py")
    assert not should_index_path("dist/bundle.js")
    assert not should_index_path("app.min.js")
    assert not should_index_path("proto/user_pb2.py")
    assert not should_index_path("logo.png")
    assert not should_index_path("README.md")


def test_should_index_path_skips_secrets() -> None:
    assert not should_index_path("config/.env.py")
    assert not should_index_path("keys/server.key")
    assert not should_index_path("certs/cert.pem")
    assert not should_index_path("aws_credentials.py")
    assert not should_index_path("secrets.py")


def test_should_index_text_skips_binary_and_huge_files() -> None:
    assert should_index_text("print('hi')")
    assert not should_index_text("abc\x00def")
    assert not should_index_text("x" * 300_000)
