from __future__ import annotations

from argus.retrieval.import_graph import build_import_graph
from argus.retrieval.ranking import rank_files


def test_python_import_graph_resolves_from_import() -> None:
    files = {
        "pkg/__init__.py": "",
        "pkg/a.py": "from pkg.b import helper\n\n\ndef use():\n    return helper()\n",
        "pkg/b.py": "def helper():\n    return 1\n",
        "pkg/unrelated.py": "x = 1\n",
    }
    graph = build_import_graph(files)
    assert ("pkg/a.py", "pkg/b.py") in graph.edges
    assert not graph.has_edge("pkg/unrelated.py", "pkg/b.py")
    assert set(graph.nodes) == set(files.keys())


def test_js_relative_import_resolution() -> None:
    files = {
        "src/index.js": "import { helper } from './lib/helper';\n",
        "src/lib/helper.js": "export function helper() { return 1; }\n",
    }
    graph = build_import_graph(files)
    assert graph.has_edge("src/index.js", "src/lib/helper.js")


def test_rank_files_prioritizes_changed_files_and_neighbors() -> None:
    files = {
        "pkg/a.py": "from pkg.b import helper\n\n\ndef use():\n    return helper()\n",
        "pkg/b.py": "def helper():\n    return 1\n",
        "pkg/unrelated.py": "x = 1\n",
    }
    graph = build_import_graph(files)

    ranked = rank_files(graph, ["pkg/b.py"], limit=10)
    paths = [r.path for r in ranked]

    assert paths[0] == "pkg/b.py"
    assert ranked[0].score == 1.0
    assert "pkg/a.py" in paths
    a_result = next(r for r in ranked if r.path == "pkg/a.py")
    assert "imports a changed file" in a_result.reasons
    # a changed file's importer should outrank a file with no relation at all
    unrelated_result = next(r for r in ranked if r.path == "pkg/unrelated.py")
    assert paths.index("pkg/a.py") < paths.index("pkg/unrelated.py")
    assert a_result.score >= unrelated_result.score


def test_rank_files_respects_limit() -> None:
    files = {f"file_{i}.py": "x = 1\n" for i in range(10)}
    graph = build_import_graph(files)
    ranked = rank_files(graph, ["file_0.py"], limit=3)
    assert len(ranked) == 3
    assert ranked[0].path == "file_0.py"
