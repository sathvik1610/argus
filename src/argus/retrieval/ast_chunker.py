"""Tree-sitter based source chunking.

Splits a source file into function/method-sized :class:`CodeChunk` objects
using each language's real grammar, instead of naive line-count windows. Class
bodies are represented by a lightweight header chunk (name + bases/signature)
so the class's *methods* are the chunks that carry full bodies into
retrieval — this avoids embedding the same method body twice (once inside the
class blob, once as its own chunk).

Falls back to a single whole-file chunk for languages without a grammar
mapping, or files tree-sitter cannot parse into any chunkable node.
"""

from __future__ import annotations

from tree_sitter import Node

from argus.models.chunk import ChunkKind, CodeChunk

FUNCTION_NODE_TYPES: dict[str, frozenset[str]] = {
    "python": frozenset({"function_definition"}),
    "javascript": frozenset({"function_declaration", "method_definition", "function_expression"}),
    "typescript": frozenset({"function_declaration", "method_definition", "function_expression"}),
    "tsx": frozenset({"function_declaration", "method_definition", "function_expression"}),
    "go": frozenset({"function_declaration", "method_declaration"}),
    "rust": frozenset({"function_item"}),
    "java": frozenset({"method_declaration", "constructor_declaration"}),
    "ruby": frozenset({"method"}),
    "c": frozenset({"function_definition"}),
    "cpp": frozenset({"function_definition"}),
    "c_sharp": frozenset({"method_declaration", "constructor_declaration"}),
    "php": frozenset({"function_definition", "method_declaration"}),
    "kotlin": frozenset({"function_declaration"}),
    "swift": frozenset({"function_declaration"}),
}

CLASS_NODE_TYPES: dict[str, frozenset[str]] = {
    "python": frozenset({"class_definition"}),
    "javascript": frozenset({"class_declaration"}),
    "typescript": frozenset({"class_declaration"}),
    "tsx": frozenset({"class_declaration"}),
    "go": frozenset({"type_declaration"}),
    "rust": frozenset({"struct_item", "impl_item", "enum_item"}),
    "java": frozenset({"class_declaration", "interface_declaration"}),
    "ruby": frozenset({"class"}),
    "cpp": frozenset({"class_specifier", "struct_specifier"}),
    "c_sharp": frozenset({"class_declaration", "interface_declaration"}),
    "php": frozenset({"class_declaration"}),
    "kotlin": frozenset({"class_declaration"}),
    "swift": frozenset({"class_declaration"}),
}

_NAME_FIELDS = ("name",)
_NAME_NODE_TYPES = frozenset(
    {"identifier", "type_identifier", "field_identifier", "constant", "property_identifier"}
)


def chunk_file(path: str, source: str, language: str | None) -> list[CodeChunk]:
    """Chunk a source file's text into function/method/class-header pieces."""
    if not language:
        return [_whole_file_chunk(path, source, language)]

    try:
        from tree_sitter_language_pack import get_parser
    except ImportError:
        return [_whole_file_chunk(path, source, language)]

    try:
        parser = get_parser(language)  # type: ignore[arg-type]
    except LookupError:
        return [_whole_file_chunk(path, source, language)]

    source_bytes = source.encode("utf-8")
    tree = parser.parse(source_bytes)

    chunks: list[CodeChunk] = []
    _walk(tree.root_node, source_bytes, language, path, chunks, parent_name=None)

    if not chunks:
        return [_whole_file_chunk(path, source, language)]
    return chunks


def _walk(
    node: Node,
    source_bytes: bytes,
    language: str,
    path: str,
    chunks: list[CodeChunk],
    parent_name: str | None,
) -> None:
    func_types = FUNCTION_NODE_TYPES.get(language, frozenset())
    class_types = CLASS_NODE_TYPES.get(language, frozenset())

    for child in node.children:
        if child.type in func_types:
            name = _node_name(child, source_bytes)
            kind = ChunkKind.METHOD if parent_name else ChunkKind.FUNCTION
            chunks.append(_make_chunk(child, source_bytes, language, path, kind, name, parent_name))
            continue  # don't descend into nested/local functions to avoid duplicate chunks

        if child.type in class_types:
            name = _node_name(child, source_bytes)
            chunks.append(_make_header_chunk(child, source_bytes, language, path, name))
            _walk(child, source_bytes, language, path, chunks, parent_name=name)
            continue

        _walk(child, source_bytes, language, path, chunks, parent_name)


def _node_name(node: Node, source_bytes: bytes) -> str | None:
    for field in _NAME_FIELDS:
        named = node.child_by_field_name(field)
        if named is not None:
            return source_bytes[named.start_byte : named.end_byte].decode("utf-8", errors="replace")
    for child in node.children:
        if child.type in _NAME_NODE_TYPES:
            return source_bytes[child.start_byte : child.end_byte].decode("utf-8", errors="replace")
    return None


def _make_chunk(
    node: Node,
    source_bytes: bytes,
    language: str,
    path: str,
    kind: ChunkKind,
    name: str | None,
    parent_name: str | None,
) -> CodeChunk:
    code = source_bytes[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
    return CodeChunk(
        file_path=path,
        language=language,
        kind=kind,
        name=name,
        parent_name=parent_name,
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        code=code,
    )


def _make_header_chunk(
    node: Node, source_bytes: bytes, language: str, path: str, name: str | None
) -> CodeChunk:
    """A class/type's declaration line(s) only, up to its body's opening brace/colon."""
    body_field = node.child_by_field_name("body")
    header_end = body_field.start_byte if body_field is not None else node.end_byte
    header = source_bytes[node.start_byte : header_end].decode("utf-8", errors="replace").rstrip()
    return CodeChunk(
        file_path=path,
        language=language,
        kind=ChunkKind.CLASS_HEADER,
        name=name,
        parent_name=None,
        start_line=node.start_point[0] + 1,
        end_line=node.start_point[0] + 1 + header.count("\n"),
        code=header,
    )


def _whole_file_chunk(path: str, source: str, language: str | None) -> CodeChunk:
    return CodeChunk(
        file_path=path,
        language=language,
        kind=ChunkKind.MODULE,
        name=None,
        start_line=1,
        end_line=source.count("\n") + 1,
        code=source,
    )
