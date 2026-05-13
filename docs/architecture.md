# BlogAgent Architecture

## Overview

BlogAgent uses a **hybrid deterministic workflow** with two model roles. The pipeline order, state transitions, schemas, validation rules, and guardrails are all deterministic Python code. LLMs are called only for tasks that require judgment: research planning, synthesis, drafting, evaluating, and revising.

This split keeps the system testable and auditable. A failing deterministic step produces a clear Python error. A failing LLM step produces a measurable eval regression.

**Current status:** Real LLM calls are not yet implemented. All LLM steps are stubs. Real web search and extraction are optional via environment configuration.

---

## Two Model Roles

### Editor Agent

Responsible for:
- Generating research questions from a topic
- Producing a structured blog outline from the evidence table
- Writing the article draft
- Revising the draft when the Fact-Check Evaluator finds blocking issues

The Editor Agent reads the evidence table before drafting. It does not draft first and search for sources later.

**Current state:** stub — returns deterministic placeholder output.

### Fact-Check Evaluator

Responsible for:
- Extracting factual claims from the draft
- Classifying each claim as `supported`, `partially_supported`, or `unsupported` against the evidence table
- Returning a structured `FactCheckReport`

The evaluator is a separate model role to enforce independence from the drafter.

**Current state:** stub — marks all claims as `supported`.

---

## Deterministic Pipeline Steps

```text
intake_topic           → normalize and validate topic string
check_external_effects → guardrail: block publishing/posting requests immediately
generate_questions     → placeholder or LLM research questions
run_web_search         → call web_search tool (mock default; Tavily optional via env)
extract_webpages       → call webpage_extract tool (httpx + BS4; mock for mock URLs)
score_sources          → call source_score tool (deterministic; no LLM)
build_evidence_table   → assemble EvidenceItem list from scored sources
generate_outline       → Editor Agent call (stub → LLM)
write_draft            → Editor Agent call (stub → LLM)
extract_claims         → Fact-Check Evaluator call (stub → LLM)
match_citations        → citation_matcher tool (stub → LLM)
run_fact_check         → assemble FactCheckReport deterministically
package_article        → assemble and validate ArticlePackage (with SEO fields)
```

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

## State Object

`BlogRunState` is a Pydantic model passed through every step. Each step receives the full state and returns the modified state. No global mutable state.

Key fields:
- `blocked: bool` — set by `check_external_effects`
- `block_reason: str` — human-readable explanation
- `requires_approval: bool` — True when an external effect was requested

See [blogagent/workflow/state.py](../blogagent/workflow/state.py) for the full schema.

---

## Article Package

The final `ArticlePackage` includes:

- `article_markdown` — the full draft
- `source_list` — scored sources
- `fact_check_report` — claim support summary
- `claim_support_statuses` — per-claim citation matches
- `revision_summary` — what changed in revision
- `title` — article title (from outline)
- `slug` — URL-safe slug (derived from title)
- `meta_description` — SEO description (stub in MVP)
- `seo_keywords` — keyword list (from outline)

---

## Validation Layer

Three deterministic validators run before the pipeline considers the article complete:

- `validate_article_package` — checks required fields are present and non-empty (including title and slug)
- `validate_minimum_sources` — enforces a minimum source count (default: 3)
- `validate_no_unsupported_high_importance_claims` — blocks finalization if any high-importance claim is unsupported

See [blogagent/tools/validators.py](../blogagent/tools/validators.py).

---

## What Is Not Here Yet

- Real LLM API calls (Editor Agent, Fact-Check Evaluator are stubs)
- Revision loop (pipeline runs once)
- CMS publishing (blocked; requires approval gate)
- Persistence / database
- Async / streaming
- Cost tracking

See [limitations.md](./limitations.md) for details.
