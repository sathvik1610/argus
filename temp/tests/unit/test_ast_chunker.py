from __future__ import annotations

from argus.models.chunk import ChunkKind
from argus.retrieval.ast_chunker import chunk_file


def test_python_chunking_separates_functions_methods_and_class_header() -> None:
    source = (
        "import os\n\n"
        "class Foo:\n"
        "    def bar(self, x):\n"
        "        return x + 1\n\n"
        "    def baz(self):\n"
        "        pass\n\n\n"
        "def top_level(y):\n"
        "    return y * 2\n"
    )
    chunks = chunk_file("foo.py", source, "python")
    kinds = {c.qualified_name: c.kind for c in chunks}

    assert kinds["Foo"] == ChunkKind.CLASS_HEADER
    assert kinds["Foo.bar"] == ChunkKind.METHOD
    assert kinds["Foo.baz"] == ChunkKind.METHOD
    assert kinds["top_level"] == ChunkKind.FUNCTION

    bar_chunk = next(c for c in chunks if c.qualified_name == "Foo.bar")
    assert "return x + 1" in bar_chunk.code
    # the class header chunk must not duplicate the full method bodies
    class_chunk = next(c for c in chunks if c.qualified_name == "Foo")
    assert "return x + 1" not in class_chunk.code


def test_javascript_chunking() -> None:
    source = (
        "class Widget {\n"
        "  constructor(x) { this.x = x; }\n"
        "  render() { return this.x; }\n"
        "}\n\n"
        "function helper(a, b) { return a + b; }\n"
    )
    chunks = chunk_file("w.js", source, "javascript")
    names = {c.qualified_name for c in chunks}
    assert names == {"Widget", "Widget.constructor", "Widget.render", "helper"}


def test_unknown_language_falls_back_to_whole_file_chunk() -> None:
    chunks = chunk_file("data.txt", "some\nunstructured\ntext\n", None)
    assert len(chunks) == 1
    assert chunks[0].kind == ChunkKind.MODULE
    assert chunks[0].code.startswith("some")


def test_unparseable_source_falls_back_to_whole_file_chunk() -> None:
    # A syntactically broken file for the declared language should not crash
    # chunking — tree-sitter parses incrementally and tolerates errors, and if
    # no chunkable node is found we fall back to a single module chunk.
    chunks = chunk_file("broken.py", "def (((invalid syntax", "python")
    assert len(chunks) >= 1
