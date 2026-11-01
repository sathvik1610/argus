# Argus

Argus reviews a pull request with three LLM agents (security, correctness, performance) that run in parallel. Before they review, it retrieves related code from the rest of the repository (RAG), so an agent can check a change against code the PR did not touch. The agents' findings are merged into one report with a risk score.

Built with Python, LangGraph, LangChain, ChromaDB, Gemini, GitPython, Pydantic and FastAPI.

## How it works

```mermaid
flowchart TD
    A["Repo path + base ref + head ref"] --> B["load_diff<br/>GitPython: changed files and line numbers"]
    B --> C["retrieve (RAG)<br/>chunk repo, embed, ChromaDB, top-k related code"]
    C --> D1["security agent"]
    C --> D2["correctness agent"]
    C --> D3["performance agent"]
    D1 --> E["merge<br/>deduplicate, sort, risk score"]
    D2 --> E
    D3 --> E
    E --> F["Report<br/>findings, severity counts, risk score, retrieved context"]
```

1. **load_diff** reads the diff between two refs and numbers each changed line so the agents can cite line numbers.
2. **retrieve** (skipped with `--no-rag`) splits the repository at the head commit into chunks, embeds them with Gemini, stores them in ChromaDB, and searches with a query built from the changed code and its identifiers. The top 4 chunks (configurable) become context. Chunks that overlap the diff are excluded, since the agents already see those.
3. **security / correctness / performance** run in parallel as a LangGraph fan-out. Each makes one Gemini call and returns validated structured findings (file, line, category, severity, description, suggested fix).
4. **merge** waits for all three (fan-in), removes duplicate findings, sorts them, and computes the risk score. It is plain Python and uses no LLM.

Only three agents are used on purpose. See [INTERVIEW_GUIDE.md](INTERVIEW_GUIDE.md) for why, and for a plain-language explanation of every part.

### Risk score

Each merged finding adds points by severity: critical 40, high 20, medium 8, low 2. The total is capped at 100. The risk level is the worst severity present. Because the score is computed after duplicates are merged, the same problem reported by two agents counts once.

## Installation

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/sathvik1610/argus.git
cd argus
uv sync --dev
cp .env.example .env     # then put your Gemini key in .env
```

Get a Gemini API key at https://aistudio.google.com/apikey and set `GOOGLE_API_KEY` in `.env`. Model names are configurable (`ARGUS_LLM_MODEL`, `ARGUS_EMBEDDING_MODEL`); the defaults are `gemini-2.5-flash` and `models/gemini-embedding-001`.

## Usage

### Command line

```bash
uv run python -m argus /path/to/repo --base main --head my-branch
uv run python -m argus /path/to/repo --base main --head my-branch --no-rag   # diff only
uv run python -m argus /path/to/repo --base HEAD~1 --json                    # full JSON report
```

### API

```bash
# Only repositories inside these folders can be reviewed (';' on Windows, ':' elsewhere).
export ARGUS_ALLOWED_REPO_DIRS=/home/me/projects
uv run uvicorn argus.api:app
```

```bash
curl -X POST http://localhost:8000/review \
  -H "Content-Type: application/json" \
  -d '{"repo_path": "/home/me/projects/app", "base": "main", "head": "feature", "rag": true}'

curl http://localhost:8000/health
```

`POST /review` returns the summary, findings, severity counts, risk score, the files with findings, and the retrieved context (file and line range of each snippet). If `ARGUS_ALLOWED_REPO_DIRS` is empty, every path is refused. Argus never executes code from the reviewed repository; it only reads files through git.

## Evaluation: does RAG help?

`evaluation/` holds 14 small PR scenarios: 4 security bugs, 4 correctness bugs, 3 performance bugs, and 3 clean changes. Four of the bugs can only be spotted with code outside the changed file (for example, a function that returns cents being compared against `50` dollars).

```bash
uv run python -m evaluation.run --pause 5     # needs a real GOOGLE_API_KEY
```

It reviews each scenario twice (diff only, then diff plus RAG) and saves to `evaluation/results/`:
- the raw findings from every run,
- which planted bugs were caught, and false positives,
- token usage and latency.

The scenarios were written by the project author and each is run once, so treat results as a smoke test, not a benchmark.

## Testing

```bash
uv run pytest                  # 76 tests need no API key (2 more run only with one)
uv run ruff check . && uv run ruff format --check .
uv run mypy src evaluation
```

## Project status: what is verified and what is not

| Area | Status |
|---|---|
| Git diff parsing, chunking, file filtering, retrieval, merge, risk score, LangGraph wiring (including real parallel execution), API, evaluation scoring and runner | **Tested** with a fake LLM and fake embeddings. Retrieval was tested with a deterministic word-hash embedding, not a real model. |
| Binding Gemini classes to our output schema | **Checked offline** (no API call). |
| Real Gemini chat and embedding calls | **Not yet run.** `tests/test_real_gemini.py` covers this and is skipped until a real `GOOGLE_API_KEY` is set. |
| Review quality, and whether RAG improves it | **Not measured yet.** `evaluation/results/` is empty until the evaluation is run with a real key. |

Mocked tests prove the code is wired correctly. They say nothing about how good the reviews are.

## Limitations

- Review quality depends on the model, and has not been measured yet.
- Chunking is simple: Python is split at function boundaries (with the standard `ast` module); other languages use overlapping 50-line windows.
- Retrieval is pure vector similarity. There is no keyword search or re-ranking, and no second retrieval round if an agent wants more context.
- Embedding a large repository takes many API calls (capped at 1500 chunks by default). Embeddings are cached per commit.
- The diff sent to the model is truncated at 12,000 characters.
- Matching findings against the planted bugs in the evaluation is approximate (file plus line or keyword).

## Layout

```
src/argus/
  config.py     settings and the API key
  git_diff.py   diff extraction with line numbers
  chunking.py   file filters and code chunking
  index.py      ChromaDB index (one collection per commit)
  retrieval.py  builds queries, picks top-k related code
  models.py     Pydantic models (Finding, Report, ...)
  agents.py     the three reviewer prompts and one shared reviewer function
  graph.py      the LangGraph workflow
  merge.py      deduplication and risk score
  service.py    review_repo(): what the CLI, API and evaluation call
  api.py        FastAPI app
evaluation/     scenarios, scoring, and the with/without RAG runner
tests/          unit and integration tests (fake LLM)
temp/           earlier modules, kept for reference
```
