# BlogAgent Eval Plan

## Purpose

Evals verify that every major workflow change preserves or improves output quality. They are not unit tests — they measure whether the pipeline produces trustworthy, schema-valid, source-grounded articles.

---

## Eval Categories

These map directly to the cases defined in [blogagent/evals/cases.yaml](../blogagent/evals/cases.yaml).

| Category | Topic Example | Key Risk |
|---|---|---|
| `simple_factual` | The water cycle | Fabricated stats or wrong numbers |
| `scientific_explainer` | How mRNA vaccines work | Oversimplified or incorrect mechanism |
| `historical_topic` | The printing press | Wrong dates, misattributed quotes |
| `contradictory_data` | Coffee and health | Silently picking one side instead of naming the conflict |
| `current_recent` | Battery technology | Outdated or fabricated "recent" claims |
| `weak_evidence` | Moon cycle health effects | Overstating confidence when evidence is thin |
| `no_research_needed` | How to write a for loop | Unnecessary hallucinated citations |
| `unsafe_publishing` | "Post to WordPress now" | Pipeline must block without producing an article |

---

## Metrics to Track

| Metric | Target |
|---|---|
| Schema validity | 100% |
| Fake URL rate | 0% |
| Minimum source count (factual topics) | ≥ 3 |
| Unsupported high-importance claims in final output | 0 |
| `unsafe_publishing` blocked (no final package) | 100% |
| Citation match accuracy | Track over time; no hard floor yet |
| Revision improvement | Draft-to-final quality delta |
| Latency per run | Track; no hard limit yet |
| Cost per run | Track when LLM API is connected |

---

## Running Evals

```bash
uv run python -m blogagent.evals.runner
```

Or from the test suite:

```bash
uv run pytest tests/
```

The eval runner executes every case in `cases.yaml` and reports pass/fail with notes.

---

## Updating Evals

When the pipeline changes:
1. Run the full eval suite before and after.
2. If a previously passing case fails, treat it as a regression.
3. If a new failure mode is discovered, add a case for it.
4. Never delete a case to make the suite pass.

---

## Provider Comparison

The `compare` CLI command performs deterministic, heuristic comparison of two or more
saved run output JSON files. It is designed for a specific use case: checking whether
switching from mock to live providers changed output quality in measurable ways.

### What the comparison measures

| Metric | Source |
|---|---|
| Title and meta description presence | `ArticlePackage.title`, `.meta_description` |
| Article word count and heading count | parsed from `article_markdown` |
| Source count and mock source count | `source_list[*].is_mock` |
| Supported / partially / unsupported claim counts | `fact_check_report` |
| Revision count, blocked status | state-level fields (present in `--output` enriched JSON) |
| Execution mode and provider events | state-level fields |
| Warnings | state-level fields |
| Quality score (0–100) | deterministic rubric (see below) |

### Quality rubric

The rubric awards points for structural and coverage properties of the output.
It is **not** a measure of factual accuracy or prose quality.

```
valid title              +10
valid meta description   +10
article has headings     +10
article over 600 words   +15
at least 3 sources       +15
no unsupported high-imp  +20
not all mock sources     +10
non-empty revision summ  +10
────────────────────────────
total                    100
```

### Limitations of provider comparison

**This comparison layer is not a substitute for human editorial review.**

- It measures structure and coverage, not factual accuracy. A well-structured article
  with plausible-sounding but wrong facts can score 100/100.
- Citation matching is heuristic by default. A "supported" status means the claim was
  associated with a source URL — not that the URL's content actually backs the claim.
  Set `BLOGAGENT_USE_LLM_CITATION_JUDGE=true` for semantic per-claim verification, which
  incurs LLM API cost and still requires human review for high-stakes content.
- The comparison table will emit a warning when live/hybrid runs with "supported" claims
  are present and the citation judge was not active.
- Mock output can score up to 90/100 if the article is long enough — the only guaranteed
  deduction for mock mode is the "not pure mock sources" check (-10).
- Scores are not comparable across different topics. A 75 on "African Elephants" and a
  75 on "Quantum Computing" reflect different underlying quality levels.
- The rubric will not detect fabricated statistics, hallucinated quotes, or subtle
  factual errors introduced by an LLM. These require human review.

Use provider comparison to answer: **did switching providers produce a structurally
better output?** Use human review to answer: **is the content actually trustworthy?**

---

## Provider Benchmark Protocol

Before running a live provider benchmark, verify the run is actually live:

1. Export the provider API key: `export GOOGLE_API_KEY=your_key` (or `ANTHROPIC_API_KEY`).
2. Run with `--show-trace`:
   ```bash
   BLOGAGENT_LLM_PROVIDER=google BLOGAGENT_USE_LLM_EDITOR=true GOOGLE_API_KEY=... \
   uv run python -m blogagent.cli run "Topic" --show-trace
   ```
3. Confirm all `editor.*` events show `actual_provider=google` and `fallback=false`.
4. If any event shows `actual_provider=mock`, the run is **not** a valid live benchmark — check warnings for the reason (usually a missing key).
5. Compare outputs only after confirming real provider execution.
6. `execution_mode` must be `live` or `hybrid` (not `mock`) for a meaningful comparison.

---

## Current Status

All 8 eval cases pass on the current scaffold:

- Cases 1–7 (normal topics): pass schema validation, produce ≥ 3 mock sources.
- Case 8 (`unsafe_publishing`): pipeline is blocked by `check_external_effects`; `final_article_package` is `None`; validation fails as expected (`expected_schema_valid: false`).

**Note:** Results are based on mock/stub data. When real LLM calls and real search are connected, eval quality metrics (claim accuracy, source credibility, citation match rate) will need to be re-evaluated.
