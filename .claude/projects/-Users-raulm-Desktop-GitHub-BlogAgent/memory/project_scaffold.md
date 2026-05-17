---
name: project-scaffold-state
description: Architecture status, what is implemented vs stub, last verified test results for BlogAgent
metadata:
  type: project
---

LLM client layer implemented in `blogagent/llm/` (schemas, providers, client, __init__).

Provider selection via `BLOGAGENT_LLM_PROVIDER` (default: mock). Anthropic/OpenAI are opt-in via `BLOGAGENT_USE_LLM_EDITOR` and `BLOGAGENT_USE_LLM_FACTCHECK` flags. Missing API keys fall back to mock with a warning — no crash.

Editor Agent has: `generate_research_plan`, `generate_outline`, `write_article_draft`, `revise_article`. All mock by default.

Fact-Check Evaluator has: `evaluate_draft`. Mock by default (deterministic from citation matches).

Claim extractor upgraded to heuristic (headings + numerical/comparative patterns). LLM call optional.

Revision loop in `graph.py`: max 1 revision. Patching for tests works via `blogagent.workflow.graph.run_fact_check` (not `nodes.run_fact_check`).

State fields added: `draft_meta_description`, `draft_seo_keywords`, `revision_summary`.

**Why:** Evidence-first architecture — LLM calls are env-gated so tests never require API keys.
**How to apply:** Use `BLOGAGENT_USE_LLM_EDITOR=true` + provider to enable real calls in production.

Last verified: 118 tests passed, 8/8 evals passed, ruff clean.
