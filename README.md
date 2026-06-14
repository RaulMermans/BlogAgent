# BlogAgent

A source-grounded editorial agent that turns a user topic into a researched, fact-checked, SEO-ready blog post.

This is not a generic AI blog generator. It is an agentic editorial workflow with web research, source extraction, source scoring, evidence tables, claim extraction, citation matching, evaluator-based revision, and final article packaging.

**Primary goal:** produce trustworthy blog drafts with visible research traces and claim-level support.

---

## About This Project

BlogAgent is an internal editorial drafting workflow for producing copy-paste-ready
blog drafts — not an autopublishing system. It combines:

- **query contracts** that lock the requested topic, count, and answer type
  before any drafting begins
- **tone profiles** that adjust voice without ever changing the underlying
  contract
- **source-aware research**, with every factual claim tied back to a scored,
  extracted source
- **candidate validation**, so recommendation lists are built from a vetted
  ledger of real entities rather than free-form generation
- **reviewer/revision agents** that audit drafts against the locked contract
  and candidate pack, and can trigger targeted repair or full rewrite
- **final answer contracts** that are the single source of truth for whether
  an article is copy-ready, needs light review, or needs revision

The output of a run is always a draft for a human editor to review and adapt —
BlogAgent does not publish, post, or send anything on its own.

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
| LLM client layer (mock default; Anthropic/OpenAI/Google optional) | **Done** |
| Editor Agent (research plan, outline, draft, revision) | **Done** — mock by default; LLM-gated via env |
| Fact-Check Evaluator (claim extraction + judgment) | **Done** — mock by default; LLM-gated via env |
| Runtime skill registry (11 skills, prompt injection) | **Done** |
| Deterministic skill selection | **Done** — fragrance/lifestyle/recommendation/personal-blog-voice |
| Quality Evaluator (deterministic, 10 checks) | **Done** |
| Quality-driven Revision Agent | **Done** — mock by default; LLM-gated via env |
| Final quality validator (post-revision, warns not blocks) | **Done** |
| Structured Agent Handoff Protocol | **Done** — locked candidates survive writer/revision/polish |
| Optional tone profile selector | **Done** — voice only; never changes contract |
| Source quality scoring (domain heuristic, high/medium/low) | **Done** |
| Heuristic claim extraction | **Done** |
| Revision loop (max 1) | **Done** |
| Heuristic citation matching (deterministic) | **Done** |
| Optional LLM semantic citation judge | **Done** — opt-in via `BLOGAGENT_USE_LLM_CITATION_JUDGE=true` |
| Evidence Sufficiency Evaluator (deterministic pre-draft gate) | **Done** |
| Targeted Enrichment Search (optional 2nd Tavily pass) | **Done** — recommendation topics only; max 2 passes |
| Publishability Evaluator (heuristic + optional LLM) | **Done** |
| Editorial Polish Agent (LLM-gated) | **Done** — runs at most once |
| Publish-ready status (`publish_ready` / `publish_ready_with_warnings` / `draft_only`) | **Done** |
| Mock/live output comparison CLI | **Done** |
| GitHub Actions CI | **Done** — mock mode, no API keys required |
| Vercel API scaffold | **Done** — mock-safe by default |
| Agent Run Trace UI panel | **Done** — includes evidence sufficiency + publishability |
| AgentPulse runtime traces | **Done** — best-effort, opt-in via env vars |
| Source quality badges in UI | **Done** |
| Staged workflow animation (16 steps, self-annotating) | **Done** |
| Query Contract + validated recommendation table | **Done** |
| Contract-aware drafting + post-draft recommendation audit | **Done** |
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

### Publish-Ready Pipeline

BlogAgent v2 adds a full publish-readiness layer on top of the existing research and drafting pipeline.

#### Evidence Sufficiency Evaluation
Before drafting, a deterministic evaluator checks whether the retrieved evidence is sufficient:
- For recommendation topics: counts validated recommendation candidates vs requested count
- If insufficient and Tavily is configured: triggers one targeted **enrichment search** pass
- Output: `evidence_sufficiency` with `sufficient`, `score`, `supported_count`, `recommended_action`

#### Query Contract
After intent detection, BlogAgent builds a deterministic `QueryContract` that defines the exact answer shape: `task_type`, `domain`, `requested_count`, `answer_entity_type`, valid/invalid item rules, required evidence fields, `minimum_publishable_items`, `evidence_limited_allowed`, and `exact_count_required`.

For `7 best parfums for summer`, the contract is `recommendation / beauty_fragrance / specific_fragrance_product`. Brand-only names, section headings, source titles, category phrases, SEO keywords, and citation-only text are rejected as valid product recommendations.

Generic product recommendation prompts now fall back to `consumer_products` instead of
`general/general_answer`. For example, `5 best affordable luxury watches` becomes
`recommendation / consumer_products / specific_product / watch` with `requested_count=5`.
This fallback covers consumer categories such as watches, luggage, backpacks, cameras,
headphones, office chairs, mattresses, coffee machines, laptops, skincare products,
kitchen gear, travel gear, and home products when no more specific domain applies.

#### Entity Candidate Ledger
Before drafting, BlogAgent extracts and classifies candidates from source titles, snippets, extracted source text, and evidence facts, then promotes only clean, source-backed entities into `state.allowed_candidates`.

The Candidate Cleanliness Gate v2 rejects malformed fragments, source titles, section headings, brand clusters, catalog/navigation residue, empty evidence spans, unknown weak sources, and truncated names such as `Tom Ford Neroli Portofino Eau de`. The locked allowed table carries `candidate_id`, canonical name, source URL/title, source quality/type, evidence span, evidence terms, and supported context.

`state.allowed_candidates` is the single allowed recommendation table used by drafting, draft candidate compliance, article audit, article grounding, publish contract, and API/UI responses. `state.validated_candidates` is retained only as a compatibility fallback.

#### Structured Agent Handoff Protocol

Recommendation stages exchange typed artifacts instead of relying on free-form agent
conversation:

```text
QueryContract → EntityCandidateLedger → CandidatePack
→ WriterHandoff → WriterOutputAudit → ReviewPacket
→ RevisionPlan → RevisionOutputAudit
→ PolishHandoff → PolishOutputAudit
→ LockedRepair → FinalAnswerContract
```

`CandidatePack` is the exact recommendation authority. It deduplicates clear aliases,
selects the final target count, locks candidate IDs/display names/source URLs, and marks
the run as `exact`, `evidence_limited`, or `below_minimum`. The writer receives a
deterministic skeleton with Quick Picks and one detail section per locked candidate.

The reviewer is contract-first: missing locked candidates, unknown entities, count drift,
and structural mismatches are high-severity defects. Revision consumes the resulting
`ReviewPacket` and `RevisionPlan`; polish receives an explicit allow/deny change list.
Deterministic locked-entity repair runs after every article-mutating stage and before the
final contract. It can restore conservative source-backed structure, but it cannot make a
below-minimum pack publish-ready.

Tone profiles (`Auto`, Editorial Magazine, Practical Buying Guide, Expert Analyst,
Personal Blog, Luxury / Premium, SEO Neutral) affect prose only. They cannot change
candidate identity, count, citations, evidence policy, safety constraints, or status.

Counted recommendation queries and concrete "best/top/recommend" entity queries must build
the candidate ledger. A counted recommendation cannot be `general/general_answer`, and a
candidate ledger status of `not_required` is treated as an internal consistency failure for
such queries.

#### Enrichment Search
When evidence is insufficient for a recommendation topic (and Tavily is active):
- Generates 3 targeted queries from the topic (e.g. "best date night perfumes editor picks")
- Runs a second Tavily pass; adds new non-duplicate sources (max 10 total)
- Re-extracts, re-scores, and rebuilds the evidence table
- Bounded to max 2 total search passes — no unbounded loops

#### Publishability Evaluator
After revision, a heuristic evaluator scores the article on publish standards (0–100):
- Checks for generic intro phrases, content-mill filler, weak editorial POV
- For fragrance/beauty topics: checks for sensory detail (notes, mood, occasion)
- For recommendation topics: checks that picks have "best for" context and rationale
- Checks source synthesis, conclusion quality, and title specificity
- Output: `publishability_evaluation` with `publish_ready`, `score`, `polish_required`, `defects`

#### Editorial Polish Agent
When `polish_required=True`, an LLM-backed polish pass:
- Strengthens intro with editorial specificity
- Adds voice, opinion language, and sensory context where evidence supports it
- Removes content-mill phrasing
- Makes evidence-limited framing reader-friendly
- Runs at most once; does not invent unsupported facts; preserves all citations

#### Post-Article Recommendation Grounding
After editorial polish, for recommendation topics, the pipeline extracts named products from the **final article** and matches them back to source evidence. This answers: "Can we prove these recommendations are grounded?"

- `extract_recommendations_from_article()` detects Quick Picks bullets, numbered/labeled headings, and bold product-name fields
- `match_article_recommendations_to_evidence()` matches each article recommendation to evidence candidates, source titles, and citation URLs
- `recommendation_candidates_summary` is updated with: `article_recommendations_count`, `grounded_recommendations_count`, `usable_count`, `unmatched_names`
- The publish contract uses this grounding to verify source backing — a recommendation present in the article but unmatched to evidence does not count as usable

#### Post-Draft Recommendation Audit
After draft/revision/polish, BlogAgent audits article recommendations against `state.allowed_candidates`. It flags recommendations outside the allowed list, brand-only recommendations for product-level fragrance contracts, section heading/source/category false positives, unsupported recommendations, and model-introduced source-grounded candidates.

The API exposes `recommendation_audit`, and the run trace includes validated candidate and audit results.

#### Draft Candidate Compliance
For recommendation topics, `DraftOutput.recommended_entities` links the draft back to allowed `candidate_id`s. If a live model omits `recommended_entities` but the markdown uses allowed candidate names, BlogAgent derives the list deterministically from the markdown.

**Hard invariants:**
- If `allowed_candidates_count == 0` and `recommended_count > 0` → **compliance fails**. The article introduced recommendations with no validated candidates.
- If `allowed_candidates_count >= requested_count`, the article must use exactly the requested number of allowed candidates and include Quick Picks. Using fewer is `draft_candidate_compliance_failed`, not evidence-limited.
- Evidence-limited status is only valid when the ledger has fewer allowed candidates than requested and the article uses all of them.

These invariants prevent the impossible states observed in production: `allowed=0, compliance=pass` or `allowed=0, count_status=satisfied`.

#### Domain Adapter Completeness
Each recommendation domain (`software_tools`, `finance`, `beauty_fragrance`, `consumer_products`, etc.) has a dedicated adapter that classifies extraction candidates. The adapter is used during both pre-draft extraction (entity classification) and post-draft audit (entity validation). A heading like "Navigating the AI Landscape for Student Success" or "The Shifting Sands of Energy: Opportunities in 2026" is rejected by the adapter before it can appear as a counted recommendation.

`GenericProductAdapter` handles product models and product lines for generic consumer-product
lists. It accepts names such as `Tissot PRX Quartz`, `Sony WH-1000XM5`, `Away Bigger
Carry-On`, and `Herman Miller Aeron`, while rejecting phrases like `affordable luxury
watches`, `buying guide`, `shop now`, `under $500`, and brand-only names when a specific
product is required.

Finance content is always framed as educational watchlist material — the pipeline enforces `not financial advice` disclaimer, no direct buy/sell language, and no performance predictions without sourced attribution.

#### Draft-Only Evidence Report Mode
When the candidate ledger fails (usable_count < minimum_publishable_items), the pipeline sets `evidence_limited_mode=True`. If the model still produces a normal "best X" recommendation article, draft compliance hard-fails and the publish contract blocks it as `draft_only_not_publish_ready`. The final response explains what was searched, why no validated candidates passed, and what sources were found.

#### DraftOutput Missing-Field Completion
When a live LLM provider (e.g. Gemini) returns valid `article_markdown` but omits `meta_description` or `seo_keywords`:
- The client synthesises missing fields deterministically from the article body (first prose paragraph → meta_description; headings → seo_keywords)
- `is_mock` remains `False`; `actual_provider` remains the live provider
- `warning` is set to `"structured_output_completed_missing_fields=true"`
- Mock fallback only happens when `article_markdown` itself is absent or unrecoverable

#### Publish Ready Status

The final `publish_ready_status` field indicates:
- `publish_ready` — article meets editorial standards, ready to post
- `publish_ready_with_warnings` — minor issues (evidence limits, low sources) but usable
- `draft_only_not_publish_ready` — significant quality gap; human editing required

**`FinalAnswerContract` is the canonical authority** (added in the Final Publish Contract Reconciliation sprint). It is built after all pipeline stages complete — drafting, revision, polish, grounding, and the publish contract check — and enforces these invariants:

| Check | Failure means |
|---|---|
| `count_status == "failed"` | → `draft_only` (always; closes regression where 3/5 used produced `publish_ready_with_warnings`) |
| `allowed_count == 0` and `article > 0` | → impossible state |
| `final_article_count < allowed_count` | → draft used fewer items than available |
| `grounded_count < final_article_count` | → ungrounded recommendations |
| `quick_picks_count ≠ final_article_count` | → Quick Picks structural mismatch |
| `title_declared_count ≠ final_article_count` | → title/body conflict |

`allowed_count` always comes from `candidate_ledger_summary.usable_count` (Cleanliness Gate v2), never from the broader `recommendation_candidates_summary` (which over-counts). The UI shows a status card with failure/warning reasons from `final_answer_contract.failure_reasons` and `warning_reasons`.

### Workflow

```text
User Topic
→ Intake Parser
→ check_external_effects   (guardrail — blocks publishing requests; extracts requested_count)
→ build_query_contract     (precise answer contract)
→ select_skills            (deterministic: fragrance/lifestyle/recommendation/financial/factual)
→ Editor Agent research plan  (skill briefs injected)
→ web_search (pass 1)
→ webpage_extract
→ source_score
→ score_source_quality     (high/medium/low per domain)
→ Evidence Table Builder
→ Candidate Table Builder  (validated recommendations before drafting)
→ Evidence Sufficiency Evaluator (deterministic pre-draft gate)
→ [if insufficient + is_recommendation + tavily active + pass_count < 2]
    → Enrichment Search    (3 targeted queries; max 10 sources total)
    → re-extract + re-score + rebuild evidence
→ CandidatePack              (deduplicated, locked final recommendation set)
→ WriterHandoff              (candidate/count/evidence/tone contract)
→ Editor Agent outline     (skill briefs injected)
→ Editor Agent draft       (skill briefs injected)
→ WriterOutputAudit + locked repair
→ ReviewPacket + RevisionPlan
→ Quality Evaluator        (10 deterministic checks; scores 0–100; score capped at 69 on HIGH defect)
→ [if HIGH-severity defect and revision_count < 1]
    → Revision Agent       (quality-driven; mock or LLM; skill briefs injected)
→ final_validate_quality   (post-revision check)
→ [if final_validation_status=failed and fixable HIGH defect and revision_count < 1]
    → Revision Agent       (final-validation-triggered; at most one revision total)
→ claim_extractor
→ citation_matcher
→ Fact-Check Evaluator
→ [if not passed and revision_count < 1]
    → Editor Agent revision
→ Publishability Evaluator (heuristic + optional LLM; scores 0–100)
→ Publish Contract (pre-polish check)
→ [if polish_required=True]
    → Editorial Polish Agent (LLM; runs at most once; skill briefs injected)
→ PolishOutputAudit + locked repair
→ ground_article_recommendations  (post-article grounding: extract recs from final article; match to evidence)
→ recommendation_audit     (article recommendations vs validated candidate table)
→ Publish Contract (post-polish + grounding check — final truth layer)
→ blog_package_validator
→ compute_publish_ready_status
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
| `BLOGAGENT_LLM_PROVIDER` | `mock` | `mock` (no key needed), `anthropic`, `openai`, or `google` |
| `BLOGAGENT_LLM_MODEL` | _(provider default)_ | Override model name (takes priority over provider-specific model vars) |
| `BLOGAGENT_LLM_TIMEOUT_SECONDS` | `60` | Timeout for LLM API calls |
| `ANTHROPIC_API_KEY` | _(empty)_ | Required when provider is `anthropic` |
| `OPENAI_API_KEY` | _(empty)_ | Required when provider is `openai` |
| `GOOGLE_API_KEY` | _(empty)_ | Required when provider is `google` |
| `BLOGAGENT_GOOGLE_MODEL` | `gemini-2.5-flash` | Google model when `BLOGAGENT_LLM_MODEL` is not set |
| `BLOGAGENT_USE_LLM_EDITOR` | `false` | Enable real LLM calls for Editor Agent |
| `BLOGAGENT_USE_LLM_FACTCHECK` | `false` | Enable real LLM calls for Fact-Check Evaluator |
| `BLOGAGENT_USE_LLM_CITATION_JUDGE` | `false` | Enable LLM semantic per-claim citation verification (incurs API cost) |

**Fallback transparency:** If a provider is configured but the API key is missing or the
package is not installed, the system falls back to mock with an explicit warning — no crash.
The warning appears in `state.warnings` and in `provider_events` (visible via `--show-trace`).
`execution_mode` reflects what **actually ran**, not what env vars requested.

**Recommended affordable live provider:** Google Gemini (`BLOGAGENT_LLM_PROVIDER=google`).

### Search provider variables

| Variable | Default | Purpose |
|---|---|---|
| `BLOGAGENT_SEARCH_PROVIDER` | `mock` | `mock` for deterministic tests; `tavily` for real search |
| `TAVILY_API_KEY` | _(empty)_ | Required when provider is `tavily` |
| `BLOGAGENT_HTTP_TIMEOUT_SECONDS` | `15` | Timeout for web requests |
| `BLOGAGENT_MAX_SEARCH_RESULTS` | `5` | Max results per query |

### AgentPulse telemetry variables

| Variable | Default | Purpose |
|---|---|---|
| `AGENTPULSE_ENABLED` | `false` | Set to `true` to enable AgentPulse trace events |
| `AGENTPULSE_URL` | _(empty)_ | Base URL for AgentPulse, e.g. `http://localhost:3000` |
| `AGENTPULSE_INGEST_KEY` | _(empty)_ | AgentPulse ingest key; never printed or included in payload metadata |
| `AGENTPULSE_PROJECT_ID` | `blog-agent` | AgentPulse project identifier |
| `AGENTPULSE_PROJECT_NAME` | `Blog Agent` | Display name in AgentPulse |
| `AGENTPULSE_WORKFLOW_ID` | `blog-agent-v1` | Workflow identifier for BlogAgent runs |
| `AGENTPULSE_DEBUG` | `false` | Print telemetry send failures without exposing secrets |

See [docs/agentpulse-integration.md](docs/agentpulse-integration.md) for the smoke
test command, real run command, and troubleshooting checklist.

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

### Google live editor (recommended affordable provider)

```bash
BLOGAGENT_LLM_PROVIDER=google \
BLOGAGENT_USE_LLM_EDITOR=true \
GOOGLE_API_KEY=your_key_here \
uv run python -m blogagent.cli run "Why elephants are the heaviest land animals" --show-trace
```

### Google low-cost mode

```bash
BLOGAGENT_LLM_PROVIDER=google \
BLOGAGENT_USE_LLM_EDITOR=true \
GOOGLE_API_KEY=your_key_here \
BLOGAGENT_GOOGLE_MODEL=gemini-2.5-flash-lite \
uv run python -m blogagent.cli run "Why elephants are the heaviest land animals" --show-trace
```

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

## Provider benchmark protocol

Before treating a run as a valid live benchmark:

1. Export the provider key: `export GOOGLE_API_KEY=your_key`
2. Run with `--show-trace` and check provider events:
   - All `editor.*` events must show `actual_provider=google` (or `anthropic`/`openai`) and `fallback=false`
   - `warnings` must be empty (warnings indicate unexpected fallbacks)
   - `execution_mode` must be `live` or `hybrid`, not `mock`
3. If any event shows `actual_provider=mock`, that stage used mock data — the run is not a valid live benchmark. Check warnings for the reason.
4. Compare outputs only after confirming real provider execution.

Mock output can appear identical to live output in terms of structure while containing only template prose. Always verify `actual_provider` before drawing quality conclusions.

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

**Score cap:** If any HIGH-severity defect is present (top-N count mismatch, missing Quick Picks, missing financial disclaimer, etc.), the score is capped at 69 regardless of other checks passing. A score ≥ 70 is required for `passes=True`.

**Evidence-limited exception:** For recommendation articles, if the article explicitly explains that the requested count cannot be met due to limited evidence (and the title does not falsely claim the full count), the top-N count mismatch defect is suppressed. The run trace labels this as `evidence_limited_count_accepted=True`.

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

## Browser Interface

BlogAgent ships a minimal browser UI. The main app URL is `/` — open it directly:

```
https://blog-agent-liart.vercel.app/
```

`/app` is an alias for the same page. `/info` returns API metadata as JSON.

No framework, no React, no Next.js — just a single FastAPI-rendered HTML page.

### Worker secret login

The interface boots into a **private access screen** when `BLOGAGENT_WORKER_SECRET` is set on the deployment. The topic input and generate tool stay hidden until the user enters the correct secret.

1. On first visit, the page calls `GET /auth-status`. If `worker_secret_required` is `false` (no secret configured), the tool is shown immediately.
2. If a secret is required, you see only the **Worker Secret** input and a **Login** button.
3. Clicking **Login** sends the entered value to `POST /auth/verify`. The server compares it against `BLOGAGENT_WORKER_SECRET` using a constant-time comparison.
4. On `200`, the secret is stored in `sessionStorage` under the key `blogagent_worker_secret` and the UI flips to the authenticated state showing **Logged in**, the topic textarea, and **Generate Blog Post**.
5. On `401`, the UI shows **Invalid or missing worker secret** and stays on the login screen.
6. Each generate request sends the stored secret in the `X-BlogAgent-Secret` header.
7. If `POST /run` returns `401`, the UI clears `sessionStorage`, returns to the login screen, and shows **Session expired or invalid worker secret. Log in again.**
8. To log out, click **Logout** — this clears `sessionStorage` (and any leftover `localStorage` keys from earlier versions).

**This is not production authentication.** Wrong secrets do not unlock the tool. There are no user accounts, sessions, OAuth, cookies, or rate limiting. `sessionStorage` reduces persistence compared to `localStorage` (it's cleared when the tab closes) but is still readable by any script on the same origin — do not use this gate for sensitive credentials.

### What the interface lets you do

- Log in with a worker secret (verified server-side; stored in `sessionStorage`)
- Enter a topic and generate a blog post
- See the title, slug, meta description, SEO keywords, article markdown, and claim/source stats
- Copy the article markdown to clipboard
- Download the article as `.md`
- Download the full JSON response

Provider events and raw JSON are collapsed in `<details>` sections and do not dominate the view.

---

## Troubleshooting

### If the login screen will not unlock

1. Click **Logout** to wipe any stale stored value from `sessionStorage`.
2. Re-enter your worker secret and click **Login**.
3. If you see **Invalid or missing worker secret**, the entered value does not match `BLOGAGENT_WORKER_SECRET` on the deployment — double-check both sides.
4. Expand the **Debug** section (after logging in) and confirm `auth_verified: true` and `secret_sent: true` appear on the next generate attempt.

`sessionStorage` is cleared automatically when the tab closes; older versions of the UI used `localStorage`, and any leftover keys from those versions are wiped on logout.

---

### If clicking Generate does nothing

1. Open Vercel logs (or browser DevTools → Network tab) and check for a `POST /run` request.
2. If no `POST /run` appears in the logs, the frontend JavaScript did not fire — check the browser console (F12) for JavaScript errors.
3. Test `POST /run` directly with curl to rule out a backend issue:
   ```bash
   curl -X POST https://YOUR-VERCEL-URL.vercel.app/run \
     -H "Content-Type: application/json" \
     -H "X-BlogAgent-Secret: your-secret" \
     -d '{"topic":"Why elephants are the heaviest land animals"}'
   ```
4. Confirm the worker secret saved in your browser matches `BLOGAGENT_WORKER_SECRET` on Vercel. A wrong secret returns `401` and clears the saved secret automatically.
5. Expand the **Debug** section on the page — it shows the request URL, response status, any error message, and whether a secret was sent.

---

## Worker Secret

By default `/run` is unprotected. Set `BLOGAGENT_WORKER_SECRET` to add a lightweight
demo gate that prevents casual use of the generation endpoint and locks the browser
UI behind a private access screen:

```bash
BLOGAGENT_WORKER_SECRET=your-secret
```

**Behavior:**

| Env var state | Effect |
|---|---|
| Unset or empty | `/run` works without a secret; the UI shows the tool immediately |
| Set to a value | The browser UI boots into a login screen; `POST /run` and `GET /run?topic=...` require a matching secret |

**How the browser UI uses the secret:**

- On load, the UI calls `GET /auth-status` to discover whether a secret is required.
- The login screen sends the typed secret to `POST /auth/verify`. On success it is stored in `sessionStorage` under `blogagent_worker_secret`. Wrong secrets do not unlock the tool.
- Every generate request sends the stored secret in the `X-BlogAgent-Secret` header.
- A `401` from `/run` clears `sessionStorage` and returns the UI to the login screen.

**How to pass the secret to the API directly:**

- Header: `X-BlogAgent-Secret: your-secret` (preferred — used by the browser UI)
- JSON body field: `worker_secret` (POST only)
- Query param: `worker_secret=your-secret` (GET only)

Comparison is constant-time (`secrets.compare_digest`). If missing or wrong, the endpoint returns `401 {"detail": "Invalid or missing worker secret"}`.

**Always public regardless of secret:** `GET /`, `GET /app`, `GET /info`, `GET /health`, `GET /auth-status`.

This is lightweight demo protection, not production auth. It has no sessions, no accounts,
no cookies, no OAuth, and no rate limiting. `sessionStorage` is browser-readable.

---

## How to request a blog post

### Via the browser UI

1. Open `/` (or `/app`) in a browser
2. If a worker secret is configured, enter it and click **Login** (otherwise you are taken straight to the tool)
3. Enter a topic
4. Click **Generate Blog Post**
5. Use **Copy article markdown**, **Download .md**, or **Download full JSON**

### Via curl

```bash
# Without secret
curl -X POST https://YOUR-VERCEL-URL.vercel.app/run \
  -H "Content-Type: application/json" \
  -d '{"topic":"Why elephants are the heaviest land animals"}'

# With secret
curl -X POST https://YOUR-VERCEL-URL.vercel.app/run \
  -H "Content-Type: application/json" \
  -H "X-BlogAgent-Secret: your-secret" \
  -d '{"topic":"Why elephants are the heaviest land animals"}'
```

---

## Skills

BlogAgent ships three Claude Code skills under `.claude/skills/`:

| Skill | Purpose |
|---|---|
| `skill-creator` | Sourced from [anthropics/skills](https://github.com/anthropics/skills). Teaches Claude Code how to create, test, and iterate on project skills. |
| `blog-post-seo-writing` | Defines how BlogAgent should structure SEO-ready article outputs: title, slug, meta description, heading rules, keyword density, and publish-readiness checklist. |
| `blog-output-evaluator` | Defines a 9-dimension rubric for judging BlogAgent article quality. Produces a structured score and blocking issue list. |

Skills are **scaffolding for Claude Code development workflows** — they do not automatically
change runtime pipeline behavior. Claude Code reads them during development to apply
consistent editorial standards and evaluation criteria when reviewing or improving BlogAgent outputs.

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

**Browser tests (open these URLs directly):**

```
/
/app
/info
/health
/run
/run?topic=Why%20elephants%20are%20the%20heaviest%20land%20animals
```

- `/` — browser UI for generating blog posts (HTML, no framework) — **main app URL**
- `/app` — alias for `/`
- `/info` — returns service info and available endpoints as JSON
- `/health` — returns `{"status":"ok",...}`
- `/run` — returns usage instructions with example GET and POST
- `/run?topic=...` — runs the full BlogAgent pipeline and returns the compact response

**Terminal POST test:**

```bash
curl -X POST https://YOUR-VERCEL-URL.vercel.app/run \
  -H "Content-Type: application/json" \
  -d '{"topic":"Why elephants are the heaviest land animals"}'
```

**Example local API call (mock mode):**

```bash
# Start the API locally with uvicorn
uvicorn api.index:app --port 8000

# GET routes (browser-friendly)
curl http://localhost:8000/
curl http://localhost:8000/run
curl "http://localhost:8000/run?topic=Why%20elephants%20are%20the%20heaviest%20land%20animals"

# POST route
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

---

## Pre-Public Release Checklist

Before making this repository public, confirm all of the following:

- [ ] `uv run pytest` (or `.venv/bin/python -m pytest`) passes with no failures
- [ ] `uv run ruff check .` passes with no errors
- [ ] `uv run python -m blogagent.evals.runner` runs cleanly
- [ ] `git diff --check` reports no whitespace errors
- [ ] No secrets in tracked files — grep for API keys, tokens, and passwords:
      `git grep -niE '(api[_-]?key|secret|token|password)\s*=\s*["'"'"'][^"'"'"' ]+'`
- [ ] No `.env` or `.env.*` files (other than `.env.example`) are tracked:
      `git ls-files | grep -E '\.env'`
- [ ] `.env.example` contains placeholders only — no real keys or URLs
- [ ] All API keys referenced in code are read from environment variables,
      never hardcoded or committed
- [ ] No client-side/browser code reads or exposes API keys
- [ ] If any key was ever committed (even in history), rotate it at the
      provider before/after making the repo public — removing it from a
      future commit does not undo prior exposure
- [ ] No local absolute paths (e.g. `/Users/...`) or personal data in tracked
      files: `git grep -n '/Users/'`
- [ ] No `logs/`, `runs/`, `outputs/`, `debug/`, or `*.log` files are tracked

---
