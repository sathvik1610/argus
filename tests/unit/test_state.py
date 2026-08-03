from __future__ import annotations

from argus.graph.state import initial_state


def test_initial_state_defaults() -> None:
    state = initial_state("/repo", "main")
    assert state["repo_path"] == "/repo"
    assert state["base_ref"] == "main"
    assert state["head_ref"] == "HEAD"
    assert state["context_expansion_rounds"] == 0
    assert state["errors"] == []


def test_initial_state_custom_head_ref() -> None:
    state = initial_state("/repo", "main", "feature-branch")
    assert state["head_ref"] == "feature-branch"
