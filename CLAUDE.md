# CLAUDE.md

Notes for working in this repository.

## What this is
Argus reviews a git diff with three LLM agents (security, correctness, performance) in a parallel LangGraph workflow, with RAG (ChromaDB + Gemini embeddings) for cross-file context. `README.md` explains the design; `INTERVIEW_GUIDE.md` explains it in plain language. `temp/` holds earlier modules for reference: do not edit or import it, and it is excluded from lint, type checks and tests.

## Commands
```bash
uv sync --dev
uv run pytest                              # 76 tests, no API key needed (2 more run only with a key)
uv run ruff check . && uv run ruff format --check .
uv run mypy src evaluation
uv run python -m argus <repo> --base <ref> [--head <ref>] [--no-rag] [--json]
uv run uvicorn argus.api:app
uv run python -m evaluation.run --pause 5  # real Gemini calls; needs GOOGLE_API_KEY
```
CI (`.github/workflows/ci.yml`) runs lint, format check, mypy and pytest; all must pass.

## Conventions
- Gemini is the only provider. The key comes from `GOOGLE_API_KEY` in `.env`; `.env.example` holds a placeholder.
- All three agents share `agents.run_reviewer`; they differ only in their prompt (`FOCUS`). The agent, not the model, sets each finding's category.
- Deduplication and the risk score are deterministic code in `merge.py`. Do not add an LLM there. The score must be computed from merged findings.
- Never call a real LLM in a unit test. Use `tests/fakes.py` (`FakeChatModel`, `FakeEmbeddings`). Real-API tests live only in `tests/test_real_gemini.py` and skip without a key.
- Keep code simple: plain functions, small files, comments for non-obvious logic.

## Do not
- Claim the real Gemini path or RAG quality is verified until `tests/test_real_gemini.py` and `evaluation.run` have actually been run with a real key. Report evaluation numbers only from saved files in `evaluation/results/`.
- Add agents, providers, retry loops or new dependencies without a stated, measured reason.
