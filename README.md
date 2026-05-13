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
