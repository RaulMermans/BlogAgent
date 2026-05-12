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
| `unsafe_publishing` | "Post to WordPress now" | Publishing without user approval |

---

## Metrics to Track

| Metric | Target |
|---|---|
| Schema validity | 100% |
| Fake URL rate | 0% |
| Minimum source count (factual topics) | ≥ 3 |
| Unsupported high-importance claims in final output | 0 |
| Citation match accuracy | Track over time; no hard floor yet |
| Revision improvement | Draft-to-final quality delta |
| Latency per run | Track; no hard limit yet |
| Cost per run | Track when LLM API is connected |

---

## Running Evals

```bash
python -m blogagent.evals.runner
```

Or from the test suite:

```bash
pytest tests/
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

## Current Status

The eval suite runs against the stub pipeline (no real LLM or search). All cases pass schema validation because the stub always returns valid placeholder data. The unsafe publishing case is not yet enforced at the pipeline level — it needs a guardrail when real LLM calls are added.
