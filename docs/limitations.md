# Current Limitations

This document describes what is intentionally not implemented or what has known constraints.

---

## LLM Provider

The **mock LLM provider is the default**. All tests and evals run without any API key.

Real LLM calls are opt-in:

| Variable | Default | Effect |
|---|---|---|
| `BLOGAGENT_LLM_PROVIDER` | `mock` | Set to `anthropic`, `openai`, or `google` for real calls |
| `BLOGAGENT_USE_LLM_EDITOR` | `false` | Set to `true` to enable LLM for research plan, outline, draft, revision |
| `BLOGAGENT_USE_LLM_FACTCHECK` | `false` | Set to `true` to enable LLM for claim extraction and judgment |

If a provider is configured but the API key is missing or the package is not installed,
the system falls back to mock mode with an **explicit warning**. No crash.

Fallback transparency: every LLM stage records `configured_provider`, `actual_provider`,
and `fallback` in `state.provider_events`. When fallback occurs, the warning is also in
`state.warnings`. Use `--show-trace` in the CLI to inspect these.

`execution_mode` reflects what **actually ran**, not what env vars requested:
- `mock` — all actual providers were mock (includes unexpected fallbacks)
- `hybrid` — some live providers succeeded, some stages used mock
- `live` — every stage used a live provider; no mock fallback

**Google Gemini** (`BLOGAGENT_LLM_PROVIDER=google`) is recommended as the affordable
default live provider. Requires `GOOGLE_API_KEY` and `google-genai` package.
Model selection: `BLOGAGENT_LLM_MODEL` > `BLOGAGENT_GOOGLE_MODEL` > `gemini-2.5-flash`.

---

## Draft Quality in Mock Mode

In mock mode, the `Editor Agent` generates substantive structured prose (not "[Placeholder content]"),
but it is **not** production-ready:

- Mock drafts do not contain real research — they use topic-aware template prose.
- Mock `meta_description` is a generic template, not SEO-optimized.
- Mock sources use `*.example.dev` domains — not real URLs.
- Mock source scores are `0.3` — not real credibility assessments.

These are intentional. Connect a real LLM provider to produce research-grounded output.

---

## Citation Matching

The default citation matcher is deterministic and heuristic:

- No sources → `unsupported`
- Only mock sources → `partially_supported`
- At least one real positive-score source → `supported`

The heuristic assigns the same status to every claim based on the overall source pool —
claims are not individually matched to the most relevant source.

**Optional: LLM semantic citation judge** (`BLOGAGENT_USE_LLM_CITATION_JUDGE=true`)

When this flag is enabled and source packets with extracted text are available, the
citation matcher calls `judge_citation_support()` per claim for semantic verification.
This judges whether the source excerpt actually supports the specific claim text.

Caveats:
- Enabling the judge incurs LLM API cost.
- The judge is bounded by the provided source excerpt — it cannot fetch new pages.
- If the LLM provider fails or the API key is missing, the judge falls back to the
  deterministic keyword-overlap heuristic with a logged warning. No crash.
- The deterministic heuristic is always preserved as the default. Removing it is not planned.

---

## Revision Loops

**Quality revision:** The quality evaluator checks for HIGH-severity defects (top-N count mismatch, missing Quick Picks, missing financial disclaimer, generic output, etc.) and triggers the Revision Agent if any are found. This quality revision runs **at most once** per pipeline run.

**Top-N count detection:** `count_recommendations()` counts Quick Picks items supporting both `- bullet` and `1. numbered` list formats. If neither format is found in the Quick Picks section, it falls back to counting `## 1.` / `## 2.` style numbered headings in the article body.

**Evidence-limited recommendation count:** When a recommendation topic requests N items but fewer are available from evidence, the pipeline can accept the reduced count without triggering a defect — provided the article explicitly states the evidence limitation and the title does not falsely claim the full N. This is logged as `evidence_limited_count_accepted=True` in the response. If the article does not explain the reduction and the title falsely claims "Top 10", the top-N mismatch defect fires as HIGH-severity.

**Final-validation safety-net revision:** After the quality-revision pass, `final_validate_quality` re-checks the draft. If a HIGH-severity fixable defect is still present (e.g., the revision did not restore the correct item count) and `revision_count < 1`, one additional Revision Agent call fires. This is the same revision budget slot — if the quality revision already ran, the final-validation revision is skipped.

**Fact-check revision:** After the fact-check, if blocking issues are found and `revision_count < 1`, the fact-check revision runs. Because quality or final-validation revision may have already consumed the revision budget, fact-check revision is skipped in that case.

Total revision budget: **1 revision pass** across quality, final-validation, and fact-check loops.

In mock mode, both revision agents return the draft mostly unchanged with an explanatory summary. The loops exist to demonstrate control flow — improving draft quality requires a real LLM provider.

Inspect `state.revision_summary` and `state.revision_count` to determine which loop ran.

---

## Source Grounding

All sources in mock mode are placeholder URLs with low scores. Claims derived from mock
evidence are classified as `partially_supported`, not `supported`. The `INFO` note in
eval output ("All sources are mock placeholders") is intentional transparency.

---

## Fact-Check Evaluator

In heuristic mode (`BLOGAGENT_USE_LLM_FACTCHECK=false`), the evaluator:
- Classifies claims by their citation match status (deterministic)
- Does not apply semantic or world-knowledge judgment to individual claims
- Cannot detect factual errors that are not captured by citation matching

In LLM mode, the evaluator uses an LLM to supplement deterministic blocking issues with
additional judgment, but is still bounded by the provided citations and sources.

---

## Runtime Skills

Editorial skills are **prompt-injected text**, not autonomous agents or tool-executing processes. They:
- Do not make function calls
- Have no persistent memory
- Cannot access the web or external APIs
- Do not change pipeline structure or step order

Skills only affect the content of the system prompt sent to the LLM. Their benefit is entirely dependent on the LLM following the injected brief. In mock mode, skills are selected but have no visible effect (mock output is deterministic regardless of prompt content).

## Source Quality Scoring

Source quality classification is a **domain heuristic**, not a live quality assessment:
- Unknown domains that are not in the explicit lists are classified as `medium` regardless of their actual editorial quality.
- The classifier does not evaluate content — a high-domain source can still have a low-quality article for a given topic.
- Domain lists are static and may become outdated as new authoritative sources emerge.

The classifier is intentionally simple. It provides a usable editorial signal without LLM calls.

## Staged Workflow Animation UI

The loading animation in the browser UI is **client-side simulation only** — it does not reflect actual pipeline stage progress. The API is a single synchronous blocking request; there is no streaming or server-sent events. The 12 step labels advance on a timer as a UX aid during the wait.

After the response arrives, the panel self-annotates with real data from the response: step states (done/warn/failed), quality score, revision summary, final validation status, and evidence-limited indicator. This annotation is cosmetic post-hoc labeling, not live progress reporting.

## Not Implemented

- **CMS publishing**: Blocked by the `check_external_effects` guardrail. Any future publishing step requires an explicit user approval gate.
- **Persistence**: `BlogRunState` is in-memory only. No database or file storage is wired up.
- **Streaming**: The pipeline is synchronous and blocking.
- **Async support**: All tools are synchronous.
- **Cost tracking**: No token counting or API cost tracking yet.
- **Browser automation**: Not planned for MVP.
- **Social posting**: Blocked by the external side-effect guardrail.
- **Streamlit on Vercel**: The Streamlit UI is not currently deployed to Vercel. The Vercel
  scaffold exposes a FastAPI API only. Deploying Streamlit to Vercel requires additional
  configuration not yet implemented.
- **Production auth**: The `BLOGAGENT_WORKER_SECRET` mechanism is a lightweight demo gate,
  not real authentication — there is no audit identity, no user accounts, no server-side
  sessions, no cookies, no roles, and no OAuth. The browser UI saves the verified secret
  in `sessionStorage`, which reduces persistence (cleared when the tab closes) compared
  to `localStorage` but is still readable by any script on the same origin. Not suitable
  for production without additional infrastructure.

## Browser UI

`GET /` is the main browser UI entry point. `GET /app` is an alias. Both return the same
single-page HTML interface rendered by FastAPI. `GET /info` returns API metadata as JSON.

The interface uses the worker secret as a lightweight login:
- The page boots into a private access screen when `BLOGAGENT_WORKER_SECRET` is set —
  the topic input and generate tool are hidden until `POST /auth/verify` returns `200`.
- The verified secret is saved in `sessionStorage` under `blogagent_worker_secret`. It is
  sent to the server only as the request body of `POST /auth/verify` and as the
  `X-BlogAgent-Secret` header on `POST /run`.
- `sessionStorage` reduces persistence (cleared when the tab is closed) but is still
  readable by any script on the same origin. This is not real authentication.
- There are no user accounts, server-side sessions, cookies, OAuth, tokens, audit
  identity, roles, or rate limiting.
- Clearing the tab / session storage removes the saved secret. Visiting the page again
  shows the login form.

Other browser UI limitations:

- Source URLs are not shown in the UI (the compact `/run` response does not include them).
  Use the CLI with `--json` or the **Download full JSON** button for source details.
- Markdown is rendered with `white-space: pre-wrap` — headings and bold text are not
  visually styled. A markdown renderer is not included in the MVP.
- The UI is not responsive on very narrow viewports (< 400 px).

## Claude Code Skills

`.claude/skills/` contains three skills for Claude Code development workflows.

**Important:** skill files do not automatically change runtime pipeline behavior.
They are read by Claude Code during development to apply consistent editorial
standards and evaluation criteria. They have no effect on the pipeline unless a
developer explicitly references them in their Claude Code session.

Current gaps:
- No evals or test cases have been run against the `blog-post-seo-writing` or
  `blog-output-evaluator` skills yet. Quality of the skills has not been measured.
- The `skill-creator` skill's optimization scripts require the `claude` CLI — they
  are not available in the Vercel deployment environment.

---

## Live LLM Quality

Live LLM output quality (Anthropic/OpenAI providers) has **not been benchmarked** in the eval
suite yet. The evals always run in mock mode. Live provider quality is expected to be
substantially better than mock mode for research grounding, outline coherence, and draft
readability — but this has not been measured.

Known gaps when using live providers:
- Citation matching is still heuristic unless `BLOGAGENT_USE_LLM_FACTCHECK=true` is also set.
  Even with LLM fact-checking, per-claim semantic matching is not implemented.
- The LLM receives only the evidence table, not the raw extracted webpage text. Long source
  passages are truncated to keep prompt size reasonable.
- Real provider calls may incur API cost. No token counting or cost tracking is implemented.

---

## Provider Events and Trace Visibility

`BlogRunState` now includes `provider_events`, `warnings`, `stage_timings`, and `execution_mode`
for diagnostic inspection after a run. These are surfaced via `--show-trace` in the CLI.

These are **diagnostic fields only** — they are not a full observability or tracing system.
They do not replace structured logging, are not persisted, and should not be used for
production monitoring.

---

## Provider Events and Benchmark Validity

Before treating a run as a "live benchmark":

1. Run with `--show-trace` and inspect `provider_events`.
2. Every LLM stage must show `actual_provider=google` (or `anthropic`/`openai`) and `fallback=false`.
3. If `actual_provider=mock` appears in any stage, that stage used mock data — the run is not a valid live benchmark.
4. `warnings` must be empty for a clean live run; warnings indicate unexpected fallbacks.
5. `execution_mode` must be `live` (all stages) or `hybrid` (some stages) — not `mock`.

---

## Enrichment Search

The optional second Tavily search pass is bounded by design:

- **Max search passes: 2** (initial + one enrichment pass). No unbounded loops.
- **Max sources total: 10.** Enrichment stops adding sources at this cap.
- Enrichment only runs when `is_recommendation=True`, `search_provider=tavily`, and `evidence_sufficiency.recommended_action="search_more"`.
- In mock mode, enrichment search is always skipped (mock sources cannot provide real named recommendations).
- Enrichment queries are heuristic — 3 targeted queries derived from the topic. They are not LLM-generated to avoid a dependency on the LLM client before drafting.

---

## Publishability Scoring

- The publishability score (0–100) is heuristic-based: it detects generic phrases, checks for sensory terms, and inspects structural patterns.
- It is not a guarantee of editorial quality. It catches clear failures (content-mill intros, no sensory detail) but cannot judge taste, originality, or depth without LLM review.
- A score of 80+ is a useful threshold but human review is still recommended before publication.
- The publishability evaluator does not read competitor articles or know what constitutes a "good" fragrance review by industry standards — it applies fixed rules.

---

## Personal Blog Voice

- The `personal-blog-voice` skill and editorial polish agent use prompt-driven instructions to improve tone.
- They do not implement true author memory or style transfer. Voice is prompt-engineered, not learned.
- The polish agent runs at most once. It cannot iterate if the result still feels flat.
- In mock mode, editorial polish returns the article unchanged with a summary message.

---

## No CMS Publishing

The pipeline does not and will not publish externally without explicit user confirmation. Topics containing publishing-intent keywords (e.g. "post to WordPress") are blocked at the guardrail. Adding a CMS publishing tool requires an approval gate before any external write.

---

## Human Review Still Recommended

Even when `publish_ready_status = "publish_ready"`, the article has not been reviewed by a human editor. It may still contain:
- Unsupported stylistic claims (phrasing that sounds authoritative but is hedged)
- Outdated information (evidence has a cut-off by search depth)
- Brand-specific inaccuracies that heuristics cannot detect
- Regional or cultural context gaps

Use the published article as a **strong draft**, not a final product.

---

## Recommended Next Steps

1. Set `BLOGAGENT_LLM_PROVIDER=google`, `BLOGAGENT_USE_LLM_EDITOR=true`, `GOOGLE_API_KEY=...` and run `--show-trace` to verify live execution.
2. Set `BLOGAGENT_USE_LLM_FACTCHECK=true` alongside a real provider and measure eval quality improvement.
3. Set `BLOGAGENT_USE_LLM_CITATION_JUDGE=true` alongside a real LLM provider and compare citation accuracy against the heuristic baseline using the `compare` CLI.
4. Add real source grounding checks in evals (count real vs. mock sources, check claim support rates).
5. Implement a persistence layer to store final article packages for review and comparison.
