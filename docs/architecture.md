# BlogAgent Architecture

## Overview

BlogAgent uses a **hybrid deterministic workflow** with two model roles. The pipeline order, state transitions, schemas, and validation rules are all deterministic Python code. LLMs are called only for tasks that require judgment: research planning, synthesis, drafting, evaluating, and revising.

This split keeps the system testable and auditable. A failing deterministic step produces a clear Python error. A failing LLM step produces a measurable eval regression.

---

## Two Model Roles

### Editor Agent

Responsible for:
- Generating research questions from a topic
- Producing a structured blog outline from the evidence table
- Writing the article draft
- Revising the draft when the Fact-Check Evaluator finds blocking issues

The Editor Agent reads the evidence table before drafting. It does not draft first and search for sources later.

### Fact-Check Evaluator

Responsible for:
- Extracting factual claims from the draft
- Classifying each claim as `supported`, `partially_supported`, or `unsupported` against the evidence table
- Returning a structured `FactCheckReport`

The evaluator is a separate model role (can be a separate prompt, separate call, or even a lighter model) to enforce independence from the drafter.

---

## Deterministic Pipeline Steps

```text
intake_topic           → normalize and validate topic string
generate_questions     → placeholder or LLM research questions
run_web_search         → call web_search tool (stub → real API)
extract_webpages       → call webpage_extract tool (stub → real HTTP)
score_sources          → call source_score tool (stub → real scoring)
build_evidence_table   → assemble EvidenceItem list from scored sources
generate_outline       → Editor Agent call (stub → LLM)
write_draft            → Editor Agent call (stub → LLM)
extract_claims         → Fact-Check Evaluator call (stub → LLM)
match_citations        → citation_matcher tool (stub → LLM)
run_fact_check         → assemble FactCheckReport deterministically
package_article        → assemble and validate ArticlePackage
```

---

## State Object

`BlogRunState` is a Pydantic model passed through every step. Each step receives the full state and returns the modified state. No global mutable state.

See [blogagent/workflow/state.py](../blogagent/workflow/state.py) for the full schema.

---

## Validation Layer

Three deterministic validators run before the pipeline considers the article complete:

- `validate_article_package` — checks required fields are present and non-empty
- `validate_minimum_sources` — enforces a minimum source count (default: 3)
- `validate_no_unsupported_high_importance_claims` — blocks finalization if any high-importance claim is unsupported

See [blogagent/tools/validators.py](../blogagent/tools/validators.py).

---

## What Is Not Here Yet

- Real LLM API calls (Editor Agent, Fact-Check Evaluator are stubs)
- Real web search (web_search tool is a stub)
- Real webpage extraction (webpage_extract tool is a stub)
- Real source scoring (source_score tool is a stub)
- Revision loop (the pipeline runs once; revision requires re-entry)
- CMS publishing (forbidden until approval gates exist)

See [limitations.md](./limitations.md) for details.
