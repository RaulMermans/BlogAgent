# BlogAgent

A source-grounded editorial agent that turns a user topic into a researched, fact-checked, SEO-ready blog post.

This is not a generic AI blog generator. It is an agentic editorial workflow with web research, source extraction, source scoring, evidence tables, claim extraction, citation matching, evaluator-based revision, and final article packaging.

**Primary goal:** produce trustworthy blog drafts with visible research traces and claim-level support.

---

## Implementation Status

| Layer | Status |
|---|---|
| Deterministic pipeline scaffold | **Done** |
| Schema validation + guardrails | **Done** |
| External side-effect blocking | **Done** |
| Mock search + extraction (default) | **Done** |
| Real search via Tavily (opt-in) | **Done** — requires `TAVILY_API_KEY` |
| Real webpage extraction via httpx+BS4 | **Done** — runs on non-mock URLs |
| Deterministic source scoring | **Done** |
| LLM client layer (mock default; Anthropic/OpenAI optional) | **Done** |
| Editor Agent (research plan, outline, draft, revision) | **Done** — mock by default; LLM-gated via env |
| Fact-Check Evaluator (claim extraction + judgment) | **Done** — mock by default; LLM-gated via env |
| Heuristic claim extraction | **Done** |
| Revision loop (max 1) | **Done** |
| Heuristic citation matching (deterministic) | **Done** |
| Optional LLM semantic citation judge | **Done** — opt-in via `BLOGAGENT_USE_LLM_CITATION_JUDGE=true` |
| Mock/live output comparison CLI | **Done** |
| GitHub Actions CI | **Done** — mock mode, no API keys required |
| Vercel API scaffold | **Done** — mock-safe by default |
| Persistence / database | Not yet |

---

## MVP Architecture

The pipeline uses a **hybrid deterministic workflow** with two model roles:

### Agents

| Agent | Role |
|---|---|
| **Editor Agent** | Research planning, outline, draft, revision |
| **Fact-Check Evaluator** | Claim extraction, citation classification |

### Tools

| Tool | Permission | Purpose |
|---|---|---|
| `web_search` | read_only | Search for sources (mock default; Tavily optional) |
| `webpage_extract` | read_only | Extract text from source URLs (httpx + BS4) |
| `source_score` | read_only | Score sources deterministically |
| `claim_extractor` | read_only | Extract factual claims from the draft |
| `citation_matcher` | read_only | Match claims to evidence sources |
| `validators` | read_only | Deterministic validation of the final package |

### Workflow

```text
User Topic
→ Intake Parser
→ check_external_effects  (guardrail — blocks publishing requests)
→ Editor Agent research plan
→ web_search
→ webpage_extract
→ source_score
→ Evidence Table Builder
→ Editor Agent outline
→ Editor Agent draft
→ claim_extractor
→ citation_matcher
→ Fact-Check Evaluator
→ [if not passed and revision_count < 1]
    → Editor Agent revision
    → claim_extractor + citation_matcher + fact-check (re-run)
→ blog_package_validator
→ Final Article Package
```

The final `ArticlePackage` always contains:
- Article markdown
- Source list with scores
- Fact-check report
- Claim support statuses
- Revision summary
- SEO fields: `title`, `slug`, `meta_description`, `seo_keywords`

Publishing to external systems is **blocked in MVP** and requires explicit user approval.

---

## Install

Requires Python 3.11+.

```bash
# With uv (recommended)
uv sync

# With pip (installs runtime + dev extras)
pip install -e ".[dev]"
```

---

## Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

### LLM provider variables

| Variable | Default | Purpose |
|---|---|---|
| `BLOGAGENT_LLM_PROVIDER` | `mock` | `mock` (no API key needed), `anthropic`, or `openai` |
| `BLOGAGENT_LLM_MODEL` | _(provider default)_ | Override model name |
| `BLOGAGENT_LLM_TIMEOUT_SECONDS` | `60` | Timeout for LLM API calls |
| `ANTHROPIC_API_KEY` | _(empty)_ | Required when provider is `anthropic` |
| `OPENAI_API_KEY` | _(empty)_ | Required when provider is `openai` |
| `BLOGAGENT_USE_LLM_EDITOR` | `false` | Enable real LLM calls for Editor Agent |
| `BLOGAGENT_USE_LLM_FACTCHECK` | `false` | Enable real LLM calls for Fact-Check Evaluator |
| `BLOGAGENT_USE_LLM_CITATION_JUDGE` | `false` | Enable LLM semantic per-claim citation verification (incurs API cost) |

**Important:** If a provider is configured but the API key is missing or the package
is not installed, the system falls back to mock mode with an explicit warning. Tests
always run in mock mode and do not require any API key.

### Search provider variables

| Variable | Default | Purpose |
|---|---|---|
| `BLOGAGENT_SEARCH_PROVIDER` | `mock` | `mock` for deterministic tests; `tavily` for real search |
| `TAVILY_API_KEY` | _(empty)_ | Required when provider is `tavily` |
| `BLOGAGENT_HTTP_TIMEOUT_SECONDS` | `15` | Timeout for web requests |
| `BLOGAGENT_MAX_SEARCH_RESULTS` | `5` | Max results per query |

---

## Run Tests

All tests run without API keys.

```bash
# With uv
uv run pytest

# With pytest directly
pytest
```

---

## Run the App

```bash
uv run streamlit run app/ui/streamlit_app.py
```

---

## Run Evals

```bash
uv run python -m blogagent.evals.runner
```

---

## Live Smoke Test

The CLI provides a single-run smoke test with configurable provider modes. All examples
below are safe to run — they do not publish externally and do not require API keys in
mock mode.

### Mock mode (default — no API keys needed)

```bash
uv run python -m blogagent.cli run "Why elephants are the heaviest land animals" --show-trace
```

Prints a summary with title, source count, claim stats, revision count, execution mode,
and (with `--show-trace`) the full provider event log and stage timings.

### Anthropic editor only

```bash
BLOGAGENT_LLM_PROVIDER=anthropic \
BLOGAGENT_USE_LLM_EDITOR=true \
ANTHROPIC_API_KEY=your_key_here \
uv run python -m blogagent.cli run "Why elephants are the heaviest land animals" --show-trace
```

### Tavily search + Anthropic editor + Anthropic fact-check

```bash
BLOGAGENT_SEARCH_PROVIDER=tavily \
TAVILY_API_KEY=your_key_here \
BLOGAGENT_LLM_PROVIDER=anthropic \
BLOGAGENT_USE_LLM_EDITOR=true \
BLOGAGENT_USE_LLM_FACTCHECK=true \
ANTHROPIC_API_KEY=your_key_here \
uv run python -m blogagent.cli run "Why elephants are the heaviest land animals" --show-trace
```

### Output flags

```bash
# Print full ArticlePackage as JSON
uv run python -m blogagent.cli run "Solar energy trends" --json

# Write JSON output to a file
uv run python -m blogagent.cli run "Solar energy trends" --output examples/live_smoke_output.json
```

Do not include real API keys in committed files or shell history.

---

## Comparing mock vs live provider outputs

BlogAgent can compare two or more saved run output JSON files and report a side-by-side
quality summary. This is useful for checking whether switching from mock to a real LLM or
search provider improved output quality.

### Produce output files

```bash
# Mock mode (no API keys needed)
uv run python -m blogagent.cli run "African Elephants" --output examples/my_mock_output.json

# Live mode (requires API keys)
BLOGAGENT_LLM_PROVIDER=anthropic \
BLOGAGENT_USE_LLM_EDITOR=true \
BLOGAGENT_SEARCH_PROVIDER=tavily \
ANTHROPIC_API_KEY=your_key \
TAVILY_API_KEY=your_key \
uv run python -m blogagent.cli run "African Elephants" --output examples/my_live_output.json
```

The `--output` flag writes an enriched JSON that includes the `ArticlePackage` fields plus
state-level metadata: `execution_mode`, `revision_count`, `provider_events`, and `warnings`.

### Compare them

```bash
uv run python -m blogagent.cli compare examples/mock_elephants_output.json examples/live_elephants_output.json
```

Example output:

```
BlogAgent Output Comparison
------------------------------------------------------------------
                                  mock_elephants_output.json      live_elephants_output.json
------------------------------------------------------------------
METADATA
  execution_mode                  mock                      live
  blocked                         False                     False
  revision_count                  0                         1
  provider_events                 5                         5
  warnings                        1                         0

ARTICLE
  has_title                       yes                       yes
  has_meta_description            yes                       yes
  word_count                      283                       682
  heading_count                   5                         6

SOURCES
  total                           3                         4
  mock                            3                         0
  real                            0                         4

CLAIMS
  total                           3                         5
  supported                       0                         4
  partially_supported             3                         1
  unsupported                     0                         0

QUALITY SCORE  (max 100)
  score                           75                        100
  deductions:
    all sources are mock          [x] mock_elephants_output [x] [ ] live_elephants_output
    under 600 words (283)         [x] mock_elephants_output [ ] live_elephants_output
```

### Quality rubric

Scores are deterministic — the same input always produces the same score.
No LLM judge is used.

| Check | Points |
|---|---|
| Valid title | +10 |
| Valid meta description | +10 |
| Article has at least one markdown heading | +10 |
| Article is over 600 words | +15 |
| At least 3 sources | +15 |
| No unsupported high-importance claims | +20 |
| Not all sources are mock placeholders | +10 |
| Revision summary is non-empty | +10 |
| **Total** | **100** |

The score is a heuristic indicator, not a substitute for editorial review.
See [docs/eval_plan.md](docs/eval_plan.md) for caveats.

---

## CI / Continuous Integration

GitHub Actions runs automatically on every push and pull request.

CI uses **mock mode** — no real API keys are required. The workflow:

1. Checks out the repo
2. Installs `uv` and Python 3.11 / 3.12
3. Runs `uv sync --all-extras`
4. Runs `uv run ruff check .` (lint)
5. Runs `uv run pytest -q` (tests)
6. Runs `uv run python -m blogagent.evals.runner` (evals)

Real provider evals (Tavily search, Anthropic/OpenAI LLM) are **manual and local** until
explicitly configured as repository secrets. Running them in CI requires adding the relevant
API keys as GitHub secrets and overriding the mock-mode env vars in the workflow.

---

## Deployment

### Streamlit UI (local / demo)

The Streamlit UI is for **local use and demos only**. Run it with:

```bash
uv run streamlit run app/ui/streamlit_app.py
```

It is **not** the Vercel deployment target.

### Vercel API (mock-safe serverless scaffold)

BlogAgent ships a minimal FastAPI app under `api/index.py` for Vercel serverless deployment.

- Defaults to **mock mode** — no environment variables required.
- Does not publish externally.
- Does not return raw scraped webpage content.
- Publishing requests are blocked by the pipeline guardrail.

**Deploy to Vercel:**

```bash
vercel deploy
```

No environment variables are required for mock mode. The API is safe to deploy and test
without any API keys.

**Required Vercel env vars for mock mode:** none.

**Optional live provider env vars (cost-bearing):**

| Variable | Purpose |
|---|---|
| `BLOGAGENT_SEARCH_PROVIDER=tavily` | Use real Tavily search |
| `TAVILY_API_KEY` | Required for Tavily |
| `BLOGAGENT_LLM_PROVIDER=anthropic` or `openai` | Use real LLM |
| `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` | Required for chosen provider |
| `BLOGAGENT_USE_LLM_EDITOR=true` | Enable LLM for Editor Agent |
| `BLOGAGENT_USE_LLM_FACTCHECK=true` | Enable LLM for Fact-Check Evaluator |
| `BLOGAGENT_USE_LLM_CITATION_JUDGE=true` | Enable semantic per-claim citation verification |

**Example local API call (mock mode):**

```bash
# Start the API locally with uvicorn
uvicorn api.index:app --port 8000

# Then call it
curl -X POST http://localhost:8000/run \
  -H "Content-Type: application/json" \
  -d '{"topic":"Why elephants are the heaviest land animals"}'
```

---

## Current Limitations

The **mock LLM provider is the default** — all LLM steps return deterministic output without
any API calls. This is intentional and ensures tests are always safe to run.

Real LLM calls are opt-in via `BLOGAGENT_USE_LLM_EDITOR=true` and/or
`BLOGAGENT_USE_LLM_FACTCHECK=true`, combined with `BLOGAGENT_LLM_PROVIDER=anthropic`
or `BLOGAGENT_LLM_PROVIDER=openai`.

Fact-checking is always bounded by the evidence actually in the evidence table — the
evaluator does not invent sources or accept claims without grounding.

Citation matching is deterministic and heuristic (no-sources → unsupported;
mock-only sources → partially_supported; real positive-score source → supported).
Semantic claim-to-source matching is not implemented unless LLM fact-checking is enabled.

See [docs/limitations.md](docs/limitations.md) for the complete list.

---

## Project Structure

```
blogagent/
  llm/        LLM client layer (provider selection, schemas, mock fallback)
  agents/     Editor Agent and Fact-Check Evaluator (mock default; LLM-gated)
  tools/      Tool implementations + deterministic validators
  workflow/   State models, pipeline nodes, graph runner
  evals/      Eval cases, runner, and graders

app/ui/       Streamlit UI

tests/        Pytest test suite
docs/         Architecture, eval plan, limitations
examples/     Sample outputs and run traces
```
