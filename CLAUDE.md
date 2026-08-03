# CLAUDE.md

Guidance for working in this repository.

## What this is

Argus: a multi-agent PR review platform. LangGraph orchestrates a graph of
five parallel specialist reviewers (security, performance, architecture,
quality, testing) plus planner/risk/consensus agents; LangChain provides the
LLM/embedding integrations. See [`docs/Architecture.md`](docs/Architecture.md)
for the full design rationale before making structural changes — it explains
*why* the graph fans out in parallel instead of chaining, why retrieval
combines AST chunking + import graph ranking + semantic search, and the
known tradeoffs/limitations. Read it first if a change touches
`src/argus/graph/`, `src/argus/retrieval/`, or `src/argus/agents/`.

## Environment

- Python 3.12, managed with `uv` (not pip/poetry/conda).
- `uv sync --dev` installs everything, including dev tools.
- Default LLM provider is Google Gemini; the project supports OpenAI,
  Anthropic, and Ollama via `ARGUS_LLM_PROVIDER` (see `.env.example`).
- No real provider API key is required to run tests, lint, type-check, or use
  `argus graph` / `argus config` / `argus doctor` — those paths are designed
  to work without network access. Only `argus review` and `POST /review`
  need a real key.

## Commands

```bash
uv run pytest                              # full test suite
uv run pytest --cov=src/argus --cov-report=term-missing   # with coverage
uv run ruff check .                        # lint
uv run ruff format .                       # format
uv run mypy src                            # type check (strict; tests/ excluded)
uv run argus graph                         # print the workflow's Mermaid diagram — no API key needed
uv run argus doctor                        # environment/config sanity check
```

All four (pytest, ruff check, ruff format --check, mypy) must pass before
committing — this matches `.github/workflows/ci.yml`.

## Testing patterns

- **Never hit a real LLM provider in tests.** Use `tests/fakes.py`'s
  `FakeStructuredChatModel`, which maps a Pydantic schema type to a
  pre-registered response (or a list of responses, consumed in order, for
  schemas invoked more than once — e.g. `RiskAssessment` across a
  context-expansion loop). Pass it as `build_review_graph(settings,
  chat_model=fake, embeddings=fake_embeddings)`.
- `tests/conftest.py`'s `temp_git_repo` fixture gives a real two-commit git
  repo on disk for repository/diff/indexing tests — prefer it over mocking
  GitPython.
- Integration tests (`tests/integration/`) exercise the full compiled graph,
  the FastAPI app via `TestClient`, and the CLI via `typer.testing.CliRunner`.
  Unit tests (`tests/unit/`) exercise one module in isolation.

## Code conventions

- Every reviewer agent shares `agents/base.py`'s `StructuredAgent` — a
  reviewer is a system prompt (`prompts/`) + a Pydantic schema
  (`models/review.py`), not new invocation plumbing. Follow this pattern if
  adding a sixth reviewer.
- Node functions in `graph/nodes.py` are factories: `make_x_node(deps) ->
  (state) -> partial_state_update`. Keep construction (needs settings/agents)
  separate from invocation (needs only state).
- `ChatModelLike` (a `Protocol` in `agents/base.py`) is the parameter type for
  anything that takes a chat model — not `BaseChatModel` directly — so tests
  and `argus graph`'s topology-only placeholder model can satisfy it
  structurally without inheriting from LangChain's base class.
- Settings (`config.py`) is a `pydantic-settings` `BaseSettings` with
  `populate_by_name=True` — provider API key fields have aliases matching
  each provider's own standard env var name (`GOOGLE_API_KEY`, not
  `ARGUS_GOOGLE_API_KEY`), and `populate_by_name` is what lets tests/callers
  construct `Settings(google_api_key=...)` by field name too. Don't remove
  this without checking both paths still work.

## Known constraints / do not "fix" these

- `ReviewState.import_graph` and `.vector_index` hold live in-process Python
  objects (a `networkx.DiGraph`, a Chroma handle), not serialized data. This
  is intentional for an in-process CLI/API service — see Architecture.md's
  tradeoffs section before "fixing" it into a serialized form.
- Import-graph-based ranking only resolves Python and JS/TS imports by
  design (see Architecture.md) — this is a deliberate scope decision, not an
  oversight to complete for every tree-sitter-supported language.
- Several `# type: ignore` comments in `services/llm.py`,
  `retrieval/vector_store.py`, and `tools/repository.py` work around
  third-party stub/runtime mismatches (documented inline at each site) — they
  are not suppressing real bugs.

## Git conventions

- Conventional commit prefixes: `feat:`, `fix:`, `test:`, `docs:`, `build:`,
  `refactor:`, `chore:`.
- Commit at the granularity of one coherent unit of work (one component, one
  fix) — not one commit per file, not one commit for the whole feature.
