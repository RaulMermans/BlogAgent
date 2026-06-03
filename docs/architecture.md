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

**DraftOutput missing-field completion**: When a live provider returns valid `article_markdown` but omits the required `meta_description` (e.g. Gemini skips the field), the client deterministically synthesises the missing field from the article body before attempting a repair call or falling back to mock:
- `meta_description`: first prose paragraph, capped at 160 characters
- `seo_keywords`: top keywords from article headings
- `is_mock` remains `False`; `provider` remains the live provider; `warning` is set to `"structured_output_completed_missing_fields=true"`

Mock fallback only happens when `article_markdown` itself is absent, empty, or irrecoverable.

**Article markdown fence stripping**: `clean_article_markdown()` strips outer `` ```markdown `` / `` ``` `` wrappers that some LLMs add around article content. Internal code fences are preserved. Applied to `DraftOutput.article_markdown` on every live provider response.

---

## Deterministic Pipeline Steps

```text
intake_topic                     → normalize topic; detect recommendation/financial intent
check_external_effects           → guardrail: block publishing requests; extract requested_count
build_query_contract             → define exact answer contract and valid entity type
select_skills                    → deterministic skill selection (fragrance/lifestyle/rec/financial/factual)
generate_research_qs             → Editor Agent: research plan (mock or LLM); skill briefs injected
run_web_search [pass 1]          → call web_search tool (mock default; Tavily optional)
extract_webpages                 → call webpage_extract tool
score_sources                    → call source_score tool (deterministic)
score_source_quality             → classify each source as high/medium/low (domain heuristic)
build_evidence_table             → assemble EvidenceItem list from scored sources
build_candidate_table            → extract and validate recommendation candidates before drafting
evaluate_evidence_sufficiency    → deterministic pre-draft gate; sets recommended_action
[if recommended_action=search_more + tavily + pass < 2]
  run_enrichment_search          → 3 targeted queries; re-extract + re-score + rebuild evidence
generate_outline                 → Editor Agent: outline (mock or LLM); skill briefs injected
write_draft                      → Editor Agent: draft (mock or LLM); skill briefs injected
evaluate_quality                 → deterministic quality checks; score capped at 69 on HIGH defect
revise_if_needed                 → Revision Agent if HIGH-severity defect (at most once)
final_validate_quality           → sets final_validation_status / final_validation_defects
revise_if_final_validation_failed → safety-net: one more revision if fixable HIGH defect
extract_claims                   → claim_extractor tool (heuristic or LLM)
match_citations                  → citation_matcher tool (deterministic heuristic)
run_fact_check                   → assemble FactCheckReport (+ optional LLM judgment)
[fact-check revision]            → Editor Agent fact-check revision + re-run
evaluate_publishability          → heuristic publish-readiness check; scores 0–100
check_publish_contract           → deterministic final truth layer; hard-fail conditions (pre-polish)
[if polish_required OR contract != publish_ready]
  run_editorial_polish           → LLM polish pass (at most once); skill briefs injected
ground_article_recommendations   → extract recs from final article; match to evidence; update summary
recommendation_audit             → compare article recs to validated candidate table
check_publish_contract           → re-run after polish + grounding to reflect improvements
package_article                  → assemble ArticlePackage (with SEO fields)
compute_publish_ready_status     → uses publish_contract as final authority
```

---

## Publish-Ready Pipeline

### Requested Count Detection

`blogagent/workflow/recommendation.py` — deterministic, no LLM.

`extract_requested_count(topic)` detects explicit list counts:
- `"7 best parfums for summer"` → 7 (digit before keyword)
- `"top 10 perfumes"` → 10 (keyword before digit)
- `"seven best perfumes"` → 7 (number word via `normalize_number_words`)
- `"a list of 7 perfumes"` → 7 (list context)
- `"recommend 5 fragrances"` → 5 (suggest context)

False-positive guards: years (1900–2099), price contexts (`under $50`), quantity phrases (`for 2 people`) are excluded.

`requested_count` is stored in state and used by evidence sufficiency, quality evaluator, publishability evaluator, publish contract, revision agent, and the final run trace.

### Query Contract

`blogagent/workflow/query_contract.py` — deterministic, no LLM.

After `check_external_effects`, the pipeline builds `state.query_contract`. The contract records:
- `task_type`
- `domain`
- `requested_count`
- `answer_entity_type`
- valid and invalid item rules
- required evidence fields
- `minimum_publishable_items`
- `evidence_limited_allowed`
- `exact_count_required`

For `7 best parfums for summer`, the contract is:

```text
recommendation / beauty_fragrance / specific_product / fragrance_product
```

That means a valid item must be a specific fragrance product with source evidence. Brand-only names (`Kilian`, `Glossier`), section headings (`How We Chose`), source titles, category phrases, SEO keywords, and citation-only text do not count.

### Recommendation Candidate Extraction

`blogagent/tools/recommendation_extractor.py` — deterministic, no LLM.

Runs during `build_evidence_table` for recommendation topics. Extracts named product/entity candidates from source titles, snippets/extracted text, and evidence text:
- Bold markdown names: `**Brand Name**`
- Numbered list items: `1. Brand Name`
- Bullet list items: `- Brand Name`
- Known brand prefix scan (fragrance/beauty brands)

Each candidate tracks:
- `normalized_name`
- `entity_type` (`specific_product`, `brand`, `section_heading`, `category`, `source_title`, `unknown`)
- `domain`
- `is_specific_product`
- `source_urls` — which sources mention it
- `source_titles` — source titles that mention it
- `source_quality` — best quality of its sources (high/medium/low)
- `evidence_terms` — source-backed scent/suitability terms
- `sensory_terms` — scent/sensory words found nearby (fragrance posts)
- `supported_context` — suitability terms (summer, tested, best for, etc.)
- `usable` — True only when the item satisfies the `QueryContract`
- `confidence` — high/medium/low
- `rejection_reason` — why the candidate cannot be used
- `low_confidence` — True if only in a single low-quality source

`state.validated_candidates` is the single allowed recommendation table used by evidence sufficiency, drafting, article audit, article grounding, publish contract, API, and UI.

### Contract-Aware Draft Generation

Recommendation draft prompts receive:
- `query_contract`
- `allowed_recommendations` (`state.validated_candidates`)
- rejected candidates and rejection reasons
- `evidence_limited_mode`
- source quality summary
- selected skills

The drafter may only recommend allowed candidates. It may not introduce products, recommend brand-only names for product-level contracts, or turn headings/source titles into recommendations. When the allowed count is below the requested count, the draft must use evidence-limited title/body framing.

### Post-Article Recommendation Grounding

`ground_article_recommendations` in `blogagent/workflow/nodes.py` — deterministic, no LLM. Runs **after editorial polish** so grounding reflects the final published text.

1. `extract_recommendations_from_article(markdown)` — extracts named recommendations from the final article:
   - Quick Picks bullets: `- **Best X:** Product Name` or `- Product Name`
   - Numbered/labeled H2–H3 headings: `## 1. Product` / `### Best X: Product`
   - Bold `**Name**: Product` fields
   - Excludes generic headings (How We Chose, Buying Tips, Final Takeaway, Sources)
   - Deduplicates by normalised name

2. `match_article_recommendations_to_evidence(article_recs, evidence_candidates, ...)` — matches each recommendation to source evidence:
   - Exact normalised name match → `high` confidence
   - Containment / partial name match → `medium` confidence
   - Brand+word overlap, evidence-table text, source title → `medium/low` confidence
   - Article citation URLs in the recommendation section → `medium` confidence
   - No match → `unmatched`

3. `build_grounded_candidates_summary(candidates, groundings)` — updates `recommendation_candidates_summary`:
   - `article_recommendations_count` — how many named products were detected
   - `grounded_recommendations_count` — how many were matched to evidence
   - `usable_count` — validated pre-draft candidate count when available
   - `unmatched_names` — names that could not be matched

The publish contract uses this grounding data to verify that article recommendations have source backing.

### Post-Draft Recommendation Audit

`state.recommendation_audit` compares final article recommendations to `state.validated_candidates`.

It reports:
- article recommendation count
- grounded/allowed recommendation count
- invalid recommendations
- unsupported recommendations
- brand-only recommendations
- section-heading false positives
- model-introduced but source-grounded candidates
- pass/fail

The audit prevents contradictions where evidence sufficiency says one usable count while article grounding counts headings or brands as valid recommendations.

### Evidence Sufficiency Evaluator

`blogagent/agents/evidence_sufficiency.py` — deterministic, no LLM.

For recommendation topics, uses actual `recommendation_candidates` when available:
- `supported_count` = number of usable candidates (not a source-count proxy)
- If `supported_count < requested_count` → `recommended_action = search_more` (triggers enrichment)
- After enrichment: if still insufficient → `evidence_limited`
- Low-source dominance and thin evidence table are penalised

Output: `EvidenceSufficiencyResult` with `sufficient`, `score`, `supported_count`, `recommended_action` (`proceed | search_more | evidence_limited`).

### Enrichment Search

`run_enrichment_search` in `blogagent/workflow/nodes.py`:
- Triggers when `recommended_action == "search_more"` and Tavily is active
- Generates 3 topic-specific queries (fragrance-aware queries for perfume topics)
- Runs up to `_MAX_SEARCH_PASSES=2` total (initial + enrichment)
- Caps sources at `_MAX_SOURCES_TOTAL=10`
- Re-extracts webpages, re-scores, re-classifies quality, re-extracts candidates, rebuilds evidence table after enrichment

### Publishability Evaluator

`blogagent/agents/publishability_evaluator.py` — heuristic, deterministic, no LLM.

Recalibrated checks:
- Generic intro phrases (content-mill openers)
- Unmet requested count (HIGH: no explanation; LOW: evidence-limited framing present)
- Editorial POV (opinion signal words)
- Recommendation depth (each pick has use-case context)
- Fragrance/beauty sensory detail (notes, mood, occasion terms) — treated as CORE for fragrance
- Source synthesis (inline citations in prose)
- Conclusion quality (not a generic wrap-up)
- Title specificity (no "ultimate guide" filler)

Advisory thresholds: `publish_ready = score >= 75 and no high defects`. `polish_required` triggers on ANY core medium defect (weak_sensory_detail, unmet_requested_count, weak_pov, thin_recommendations) or score < 80 or ≥2 medium/high defects.

The publish contract is the final authority; the publishability evaluator is advisory.

### Publish Contract (Final Truth Layer)

`blogagent/agents/publish_contract.py` — deterministic, no LLM.

Hard-fail conditions that override everything else:

| Defect | Severity | Score Cap |
|---|---|---|
| Missing Quick Picks section | HIGH | 65 |
| Fewer than 3 recommendations | HIGH | 65 |
| Unmet requested count without valid evidence-limited explanation | HIGH | 59 |
| Invalid recommendations outside query contract | HIGH | 59 |
| Insufficient validated candidates | HIGH | 65 |
| Weak source dominance (>60% low-quality) | MEDIUM | 74 |
| Weak sensory detail in fragrance post | HIGH (<3 terms) / MEDIUM (3–5) | 79 |
| Insufficient recommendation depth | MEDIUM | 74 |
| Generic intro with no editorial POV | MEDIUM | 79 |
| Thin article (<200 words) | HIGH | 65 |

Status rules:
- `publish_ready` — score ≥ 85, no high defects, no unresolved count mismatch
- `publish_ready_with_warnings` — score ≥ 75, no high defects, evidence-limited count accepted
- `draft_only_not_publish_ready` — score < 75 or any high defect

`state.publish_contract` is set twice: once before editorial polish, once after. The post-polish result is used by `compute_publish_ready_status` as the final truth.

### Editorial Polish Agent

`blogagent/agents/editorial_polish_agent.py` — LLM-gated (`BLOGAGENT_USE_LLM_EDITOR=true`).

Triggers when `publishability_evaluation.polish_required=True` OR `publish_contract.status != "publish_ready"`.

- Runs at most once per pipeline
- Improves intro, voice, sensory detail, and conclusion
- Does not invent unsupported facts
- Preserves all citations and financial disclaimers
- For evidence-limited articles: frames the reduced count elegantly
- Mock fallback: returns article unchanged with explanatory summary

### New Skills

Five new skills added to `blogagent/skills/specs.py`:

| Skill | Applies To | Role |
|---|---|---|
| `beauty-fragrance-writing` | perfume/fragrance/cologne topics | Sensory language, notes, occasion, mood |
| `fashion-lifestyle-editorial` | beauty/fashion/lifestyle topics | Curated, opinionated editorial voice |
| `product-recommendation-depth` | all recommendation topics | Per-pick use case, pros/caveats |
| `personal-blog-voice` | all topics | Editorial confidence, cleaner prose |
| `publishability-review` | all topics | Pre-publication quality gate reminder |

### State Fields

```python
requested_count: Optional[int]             # count from topic ("7 best…" → 7)
recommendation_candidates: list[dict]      # RecommendationCandidate dicts
recommendation_candidates_summary: dict    # {usable_count, low_confidence_count, names}
evidence_sufficiency: Optional[dict]       # EvidenceSufficiencyResult dict
search_pass_count: int = 1                 # total search passes run
enrichment_queries: list[str]              # queries used in enrichment pass
publishability_evaluation: Optional[dict]  # PublishabilityEvaluation dict
polish_summary: list[str]                  # editorial polish change summary
publishability_score: int = 0             # convenience field from evaluation
publish_contract: Optional[dict]           # PublishContractResult dict (final truth)
publish_ready_status: str                  # mirrors publish_contract.status
```

### Source Quality Classification

`blogagent/tools/source_quality.py` — domain heuristic, no LLM.

High quality domains now include beauty/lifestyle editorial:
`byrdie.com`, `allure.com`, `vogue.com`, `harpersbazaar.com`, `elle.com`, `cosmopolitan.com`, `thecut.com`, `whowhatwear.com`, `gq.com`, `esquire.com`, `independent.co.uk`

Medium quality domains include retailer/editorial hybrids:
`fragrantica.com`, `scentbird.com`, `sephora.com`, `ulta.com`, `thebeautylookbook.com`

Low quality: social platforms — `reddit.com`, `quora.com`, `instagram.com`, `tiktok.com`, `pinterest.com`, `youtube.com`

---

## Quality Evaluator and Evaluator-Optimizer Loop

After drafting, `evaluate_quality` runs deterministic checks:

| Check | Severity | Condition |
|---|---|---|
| Top-N count mismatch | HIGH | Requested N in topic, Quick Picks has different count (counted via `count_recommendations()` which handles both `- bullet` and `1. numbered` list formats) |
| Quick Picks missing | HIGH | Recommendation article has no Quick Picks section |
| Financial disclaimer missing | HIGH | Financial topic has no disclaimer |
| Direct buy/sell language | HIGH | Draft contains "buy this stock", "invest in X now", etc. |
| Weak source dominance | HIGH (rec) / MEDIUM | >60% of sources are low quality |
| Repeated text | MEDIUM | Text blocks repeated across sections |
| No H1 title | MEDIUM | Draft has no `# Heading` |
| Fewer than 2 headings | LOW | Draft structure is weak |
| Generic/placeholder output | HIGH | Draft is under 100 chars or contains [Placeholder] |
| Missing Final Takeaway | LOW | Recommendation article missing closing section |

**Score cap:** If any HIGH-severity defect is present, the quality score is capped at 69 regardless of other checks. `passes = score >= 70`. A draft with a HIGH defect always triggers `revision_required=True`.

**Evidence-limited exception:** When checking top-N count, if the article explicitly explains that fewer recommendations are provided due to limited evidence (and the title does not falsely claim the full count), the mismatch defect is suppressed. This is recorded in `state.evidence_limited_count_accepted`.

If any HIGH-severity defect is present, `revision_required=True` and `revise_if_needed` calls the **Revision Agent** (mock or LLM). This quality revision runs **at most once**.

### Final Validation and Safety-Net Revision

`final_validate_quality` re-checks post-revision and sets `state.final_validation_status` (`"passed"` / `"passed_with_warnings"` / `"failed"`) and `state.final_validation_defects` (structured list with `severity`, `message`, `fixable` fields). Unlike earlier design, it no longer only appends flat warning strings.

`revise_if_final_validation_failed` then inspects the result: if `final_validation_status == "failed"` and there is at least one HIGH-severity `fixable` defect, and `revision_count < 1`, it triggers one additional Revision Agent call. After revision, `final_validate_quality` re-runs so the updated status is reflected in the output.

The total revision budget across all paths is **1 revision pass**.

## Fact-Check Revision Loop

After the initial fact-check, if `fact_check_report.passed = False` and `revision_count < 1`:

1. `editor_agent.revise_article()` is called (mock or LLM)
2. `state.draft` is replaced with the revised markdown
3. `state.revision_summary` is set
4. `state.revision_count` is incremented
5. Claim extraction, citation matching, and fact-check re-run

The total revision budget across quality + final-validation + fact-check revisions is **1**. In mock mode, the revision returns the draft unchanged with an explanatory summary — no infinite loop is possible.

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

## Runtime Skill Registry

Six editorial skills are defined in `blogagent/skills/specs.py`. Each skill has a name and a compressed 1-3 line brief. Skills are selected deterministically based on topic intent and injected into agent prompts as plain text before LLM calls.

| Skill | Selected when |
|---|---|
| `recommendation-writing` | Topic is recommendation-style |
| `financial-safety` | Topic involves financial/investment content |
| `source-quality-assessment` | Recommendation or financial topic |
| `citation-grounding` | Always (factual, recommendation, financial) |
| `seo-blog-writing` | Always |
| `editorial-revision` | Recommendation or financial topic |

Skills are **prompt-injected text**, not autonomous tools or agents. They do not make function calls, have no memory, and do not change pipeline structure. Skill selection is fully deterministic: no LLM involved.

## Source Quality Scoring

After `score_sources`, `score_source_quality` classifies each source as `high`, `medium`, or `low` quality using domain heuristics (`blogagent/tools/source_quality.py`):

- **Low:** Quora, Reddit, Instagram, TikTok, Pinterest, Twitter/X, Facebook, Tumblr, Yelp, Yahoo Answers, Ask.com — or any mock placeholder source.
- **High:** Wikipedia, Britannica, BBC, Reuters, AP, NYT, Guardian, WaPo, Wired, Nature, Science, NIH, CDC, WHO, Wirecutter, PCMag, TechRadar, Fragrantica, and other recognised editorial/expert publications; `.edu` and `.gov` TLDs.
- **Medium:** all other domains.

Source quality scores are stored in `state.source_quality_scores` and used by:
- The quality evaluator (triggers `weak_source_dominance` defect if >60% low)
- The Revision Agent prompt (provides source quality context)
- The UI source panel (renders quality badges)

## State Object

`BlogRunState` is a Pydantic model passed through every step. Each step receives the full state and returns the modified state. No global mutable state.

Key fields:
- `blocked: bool` — set by `check_external_effects`
- `block_reason: str` — human-readable explanation
- `requires_approval: bool` — True when an external effect was requested
- `selected_skills: list[str]` — editorial skills selected for this topic
- `requested_count: int | None` — extracted from topic (e.g. "top 10" → 10)
- `source_quality_scores: list[dict]` — per-source quality classification
- `quality_evaluation: dict | None` — output of QualityEvaluationOutput
- `final_validation_warnings: list[str]` — legacy flat warning strings from final_validate_quality
- `final_validation_defects: list[dict]` — structured defects with `severity`, `message`, `fixable` fields
- `final_validation_status: str` — `"passed"` | `"passed_with_warnings"` | `"failed"`
- `evidence_limited_count_accepted: bool` — True when fewer recommendations than requested were accepted due to evidence limits
- `run_trace: list[str]` — human-readable ✓/⚠/✗ agent run trace for the UI
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

The UI features:
- **Staged workflow animation**: 12 steps animate sequentially while the pipeline runs (Planning → Selecting skills → Researching → Searching sources → Extracting pages → Scoring sources → Building evidence table → Writing draft → Evaluating quality → Fact-checking → Packaging → Done). After the API response arrives, the panel self-annotates: it marks failed steps, shows high-severity defect banners, renders the evidence-limited pill if applicable, and displays the revision summary. This is a client-side simulation — the API is a single synchronous blocking request; no streaming or polling is implemented.
- **Agent Run Trace panel**: collates all pipeline step outcomes as ✓/⚠/✗ lines (from `state.run_trace`), showing intent, skills, search provider, source quality, draft provider, quality score, revision outcome, final validation status, and evidence-limited indicator.
- **Source quality panel**: each source is shown with a `high`/`medium`/`low` badge and a one-line reason.
- **Quality score stat pill**: displays the quality evaluator score and pass/fail.
- **Final validation defect banner**: if `final_validation_status == "failed"`, a high-severity warning banner appears above the article listing each fixable defect.

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
