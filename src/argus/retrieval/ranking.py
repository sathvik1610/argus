"""Rank repository files by relevance to a PR, using personalized PageRank
seeded on the changed files.

Diff-touched files always rank first. Beyond that, a file matters to the
review roughly in proportion to how closely it's coupled to what changed —
callers of a changed function, modules a changed file imports, and so on.
Personalized PageRank captures that transitively (a file two hops from the
diff but heavily relied upon still surfaces) without the cost of manually
walking the graph to a fixed depth.
"""

from __future__ import annotations

import networkx as nx

from argus.models.ranking import RankedFile


def rank_files(
    graph: nx.DiGraph,
    changed_paths: list[str],
    *,
    limit: int,
) -> list[RankedFile]:
    """Return up to ``limit`` files ordered by relevance to ``changed_paths``.

    Changed files are always included and ranked above everything else. The
    remaining slots go to the highest personalized-PageRank files not already
    in the changed set.
    """
    changed_set = {p for p in changed_paths if p in graph}
    ranked: list[RankedFile] = [
        RankedFile(path=p, score=1.0, reasons=["changed in this PR"]) for p in changed_paths
    ]

    remaining_budget = max(limit - len(ranked), 0)
    if remaining_budget == 0 or graph.number_of_nodes() == 0:
        return ranked[:limit]

    personalization: dict[str, float] | None = {
        node: (1.0 if node in changed_set else 0.0) for node in graph.nodes
    }
    if personalization is not None and not any(personalization.values()):
        # No changed file is a known graph node (e.g. brand-new file with no
        # resolvable imports yet) — fall back to plain centrality.
        personalization = None

    try:
        scores = nx.pagerank(graph, personalization=personalization, weight=None)
    except nx.PowerIterationFailedConvergence:
        scores = dict.fromkeys(graph.nodes, 0.0)

    candidates = [(path, score) for path, score in scores.items() if path not in changed_set]
    candidates.sort(key=lambda item: item[1], reverse=True)

    for path, score in candidates[:remaining_budget]:
        reasons = []
        if any(graph.has_edge(path, c) for c in changed_set):
            reasons.append("imports a changed file")
        if any(graph.has_edge(c, path) for c in changed_set):
            reasons.append("imported by a changed file")
        if not reasons:
            reasons.append("structurally central to the repository")
        ranked.append(RankedFile(path=path, score=float(score), reasons=reasons))

    return ranked
