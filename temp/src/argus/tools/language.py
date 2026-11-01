"""File-extension based language detection.

Shared by diff parsing (to tag `FileDiff.language`) and the tree-sitter chunker
(to select a parser). Deliberately extension-based rather than content-sniffed:
it is fast, deterministic, and covers the languages Argus actually parses.
"""

from __future__ import annotations

from pathlib import Path

_EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".hpp": "cpp",
    ".cs": "c_sharp",
    ".php": "php",
    ".kt": "kotlin",
    ".swift": "swift",
}

# Languages tree-sitter-language-pack can parse and that our chunker supports.
SUPPORTED_LANGUAGES = frozenset(_EXTENSION_TO_LANGUAGE.values())


def detect_language(path: str) -> str | None:
    """Return the language name for a file path, or None if unrecognized."""
    return _EXTENSION_TO_LANGUAGE.get(Path(path).suffix.lower())


def is_source_code(path: str) -> bool:
    return detect_language(path) is not None
