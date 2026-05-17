# BlogAgent Architecture

## Overview

BlogAgent uses a **hybrid deterministic workflow** with two model roles. The pipeline order, state transitions, schemas, validation rules, and guardrails are all deterministic Python code. LLMs are called only for tasks that require judgment: research planning, synthesis, drafting, evaluating, and revising.

This split keeps the system testable and auditable. A failing deterministic step produces a clear Python error. A failing LLM step produces a measurable eval regression.

**LLM calls are optional and environment-gated.** The default provider is `mock`, which produces deterministic output without any API key. Real LLM calls require explicit opt-in via environment variables.

---

## Two Model Roles

### Editor Agent

Responsible for:
- Generating research questions from a topic
- Producing a structured blog outline from the evidence table
- Writing the article draft
- Revising the draft when the Fact-Check Evaluator finds blocking issues

The Editor Agent reads the evidence table before drafting. It does not draft first and search for sources later.

**Gate:** controlled by `BLOGAGENT_USE_LLM_EDITOR` (default: `false` → mock output).

### Fact-Check Evaluator

Responsible for:
- Extracting factual claims from the draft (heuristic or LLM)
- Classifying each claim as `supported`, `partially_supported`, or `unsupported` against the evidence table
- Returning a structured `FactCheckJudgmentOutput` and `FactCheckReport`

The evaluator is a separate model role to enforce independence from the drafter. It judges only against the provided claims, citation matches, and source scores — it never invents sources.

**Gate:** controlled by `BLOGAGENT_USE_LLM_FACTCHECK` (default: `false` → deterministic heuristic).

---

## LLM Client Layer

The LLM client (`blogagent/llm/`) provides a single internal interface:

```python
generate_structured(
    system_prompt: str,
    user_prompt: str,
    output_model: type[BaseModel],
    temperature: float = 0.2,
) -> LLMResult
```

`LLMResult` contains: `data`, `provider`, `model`, `is_mock`, `warning`, `error`, `raw_text`.

**Provider selection via `BLOGAGENT_LLM_PROVIDER`:**

| Value | Behavior |
|---|---|
| `mock` (default) | Deterministic structured output, no API call. `is_mock=True`, `configured_provider="mock"`. |
| `anthropic` | Calls Anthropic API. Requires `ANTHROPIC_API_KEY`. Falls back to mock if key is missing. |
| `openai` | Calls OpenAI API. Requires `OPENAI_API_KEY`. Falls back to mock if key is missing. |
| `google` | Calls Google Gemini API via `google-genai`. Requires `GOOGLE_API_KEY`. Falls back to mock if key is missing. Recommended affordable live provider. |

Every `LLMResult` exposes `configured_provider` (what was requested) and `provider` (what ran).
When fallback occurs, `is_mock=True` and `warning` contains the reason (e.g. "GOOGLE_API_KEY is not set").

The mock provider has registered responses for every output schema. All tests run against the mock provider.

---

## Deterministic Pipeline Steps

```text
intake_topic             → normalize and validate topic string
check_external_effects   → guardrail: block publishing/posting requests immediately
generate_research_qs     → Editor Agent: research planning (mock or LLM)
run_web_search           → call web_search tool (mock default; Tavily optional via env)
extract_webpages         → call webpage_extract tool (httpx + BS4; mock for mock URLs)
score_sources            → call source_score tool (deterministic; no LLM)
build_evidence_table     → assemble EvidenceItem list from scored sources
generate_outline         → Editor Agent: outline (mock or LLM)
write_draft              → Editor Agent: draft (mock or LLM)
extract_claims           → claim_extractor tool (heuristic or LLM)
match_citations          → citation_matcher tool (deterministic heuristic)
run_fact_check           → assemble FactCheckReport (+ optional LLM judgment)
[revision loop]          → Editor Agent revision + re-run claims/citations/fact-check
package_article          → assemble and validate ArticlePackage (with SEO fields)
```

---

## Revision Loop

After the initial fact-check, if `fact_check_report.passed = False` and `revision_count < 1`:

1. `editor_agent.revise_article()` is called (mock or LLM)
2. `state.draft` is replaced with the revised markdown
3. `state.revision_summary` is set
4. `state.revision_count` is incremented
5. Claim extraction, citation matching, and fact-check re-run

The loop runs **at most once** (`_MAX_REVISIONS = 1`). In mock mode, the revision returns the draft unchanged with an explanatory summary — no infinite loop is possible.

---

## External Side-Effect Guardrail

The pipeline's second step is `check_external_effects`. If the topic contains publishing, posting, or sending keywords, the pipeline sets `state.blocked = True` and exits immediately without running the article workflow. The `final_article_package` remains `None`, which causes all validators to fail — this is intentional.

Publishing to external systems is forbidden in MVP. Any future publishing tool must require explicit user confirmation.

---

## Search Provider

`web_search` supports two providers, selected via `BLOGAGENT_SEARCH_PROVIDER`:

| Provider | Behavior |
|---|---|
| `mock` (default) | Deterministic mock `SearchResult` objects. Safe for testing. `is_mock=True`. |
| `tavily` | Real Tavily Search API call. Requires `TAVILY_API_KEY`. Falls back to mock if key is missing or call fails. |

---

## Webpage Extraction

`webpage_extract` uses httpx + BeautifulSoup4:

- **Mock URLs** (matching `*.example.dev`, `*.example.com`, etc.) return mock `SourcePacket` without network calls.
- **Real URLs** make an HTTP GET request, extract title/author/date/text, and bound text at 10,000 chars.
- **Failures** return an error `SourcePacket` with `extraction_status="failed"` and `error_message`. They do not raise.

---

## Source Scoring

`source_score` is fully deterministic — no LLM:

- **Mock sources** (`is_mock=True` or `extraction_status="mock"`) receive uniform low scores (0.3) and are flagged `is_mock=True`.
- **Failed extractions** receive zero scores.
- **Real sources** are scored on: domain credibility (known trusted domains, .edu/.gov TLDs), keyword overlap with the topic, and publication year if available.

---

## Citation Judge (Optional)

`blogagent/agents/citation_judge.py` provides optional LLM-backed semantic citation verification.

Controlled by `BLOGAGENT_USE_LLM_CITATION_JUDGE` (default: `false`).

When enabled, `citation_matcher` calls `judge_citation_support(claim, source_excerpt, source_url)`
per claim using the combined extracted text from available sources.

The judge:
- Uses `generate_structured()` with `CitationJudgmentOutput` (same LLM client as other agents)
- Falls back to a deterministic keyword-overlap heuristic on any failure (no crash)
- Never uses outside knowledge — judges only the provided source excerpt
- Never invents sources or fabricates references

The deterministic heuristic is always preserved as the default. The judge is additive.

---

## Claim Extraction

`claim_extractor` has two modes:

- **Heuristic (default):** parses markdown headings and body sentences. Numerical/comparative patterns (percentages, "more than", "doubled", etc.) produce `high` importance claims; structural heading phrases produce `medium` claims.
- **LLM (opt-in):** calls `generate_structured` with `ClaimExtractionOutput` schema. Enabled via `BLOGAGENT_USE_LLM_FACTCHECK=true`. Falls back to heuristic if the call fails.

---

## Provider Events and execution_mode

`BlogRunState.provider_events` contains one entry per stage that called an LLM or search provider. Each event records the configured provider, the actual provider, the model used, and whether a fallback occurred:

```
editor.research_plan: configured_provider=mock actual_provider=mock model=mock-1.0 fallback=false
editor.draft: configured_provider=anthropic actual_provider=mock model=mock-1.0 fallback=true warning="ANTHROPIC_API_KEY is not set"
editor.outline: configured_provider=google actual_provider=google model=gemini-2.5-flash fallback=false
```

When a configured live provider falls back to mock, the warning is also appended to `state.warnings`.

`execution_mode` is computed **after** the pipeline runs by inspecting the actual provider used in each event:

| Value | Meaning |
|---|---|
| `mock` | All actual providers were mock (no live provider succeeded) |
| `hybrid` | At least one live provider succeeded; at least one stage used mock |
| `live` | Every stage used a live provider; no mock fallback occurred |

This means `execution_mode=mock` when a configured live provider falls back due to a missing key. Do not report hybrid merely because env vars requested live behavior.

---

## State Object

`BlogRunState` is a Pydantic model passed through every step. Each step receives the full state and returns the modified state. No global mutable state.

Key fields:
- `blocked: bool` — set by `check_external_effects`
- `block_reason: str` — human-readable explanation
- `requires_approval: bool` — True when an external effect was requested
- `draft_meta_description: str` — SEO description from `DraftOutput`
- `draft_seo_keywords: list[str]` — keywords from `DraftOutput`
- `revision_summary: str` — what changed in revision
- `revision_count: int` — number of revisions performed (capped at 1)
- `warnings: list[str]` — fallback warnings from LLM stages; empty in pure mock mode
- `provider_events: list[str]` — one entry per stage with actual provider details

See [blogagent/workflow/state.py](../blogagent/workflow/state.py) for the full schema.

---

## Article Package

The final `ArticlePackage` includes:

- `article_markdown` — the full draft (revised if revision occurred)
- `source_list` — scored sources
- `fact_check_report` — claim support summary
- `claim_support_statuses` — per-claim citation matches
- `revision_summary` — what changed in revision (or "No revision performed.")
- `title` — article title (from outline)
- `slug` — URL-safe slug (derived from title)
- `meta_description` — SEO description (from `DraftOutput` or generic fallback)
- `seo_keywords` — keyword list (from `DraftOutput` or outline)

---

## Validation Layer

Three deterministic validators run before the pipeline considers the article complete:

- `validate_article_package` — checks required fields are present and non-empty (including title and slug)
- `validate_minimum_sources` — enforces a minimum source count (default: 3)
- `validate_no_unsupported_high_importance_claims` — blocks finalization if any high-importance claim is unsupported

See [blogagent/tools/validators.py](../blogagent/tools/validators.py).

---

## Vercel API

`api/index.py` is a minimal FastAPI application for serverless deployment.

It exposes:
- `GET /` — service info
- `GET /health` — returns service status (always 200, no pipeline required)
- `GET /app` — browser UI rendered as a single FastAPI `HTMLResponse`; no framework, no React
- `GET /run?topic=...` — browser-friendly pipeline trigger
- `POST /run` — runs the BlogAgent pipeline on a `topic` string

The API defaults to **mock-safe mode**: if no provider environment variables are set,
all pipeline steps use mock mode with no API calls. Real providers can be enabled via
Vercel environment variables (see README.md).

The API response is compact: it includes the article markdown, source count, claim status
counts, slug, SEO keywords, and diagnostic fields. Raw scraped webpage text is never returned.

Publishing requests are blocked by the same `check_external_effects` guardrail used by the
full pipeline.

### Worker secret (optional)

Set `BLOGAGENT_WORKER_SECRET` to protect `/run` endpoints with a lightweight demo gate.
When set, `POST /run` and `GET /run?topic=...` require the secret via `X-BlogAgent-Secret`
header, `worker_secret` JSON body field, or `worker_secret` query param.

`GET /`, `GET /health`, and `GET /app` are always public.

This is not production auth — there are no sessions, accounts, or rate limiting.

### Browser UI

`GET /app` returns a single-page HTML interface. It calls `POST /run` with `fetch()`,
renders the article in a blog card using `white-space: pre-wrap`, and provides buttons
to copy the markdown, download `.md`, and download the full JSON response.
Provider events and raw JSON are accessible via `<details>` sections.

---

## Claude Code Skills

Three skills live under `.claude/skills/`:

| Skill | Source | Purpose |
|---|---|---|
| `skill-creator` | [anthropics/skills](https://github.com/anthropics/skills) | Teach Claude Code how to create, test, and improve project skills |
| `blog-post-seo-writing` | Project-specific | Define the editorial standard for BlogAgent article outputs |
| `blog-output-evaluator` | Project-specific | 9-dimension rubric for grading BlogAgent article quality |

Skill files are **development scaffolding**: they do not automatically change runtime pipeline
behavior. Claude Code reads them when developing or reviewing BlogAgent to apply consistent
standards. Runtime pipeline behavior is controlled by Python code and env vars only.

---

## What Is Not Here Yet

- CMS publishing (blocked; requires approval gate)
- Persistence / database
- Async / streaming
- Cost tracking
- Streamlit on Vercel (Vercel scaffold is FastAPI only)
- Production auth (the worker secret is a lightweight demo gate only)

See [limitations.md](./limitations.md) for details.
