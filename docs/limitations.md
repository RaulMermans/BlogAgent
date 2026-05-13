# Current Limitations

This document describes what is intentionally not implemented or what has known constraints.

---

## LLM Provider

The **mock LLM provider is the default**. All tests and evals run without any API key.

Real LLM calls are opt-in:

| Variable | Default | Effect |
|---|---|---|
| `BLOGAGENT_LLM_PROVIDER` | `mock` | Set to `anthropic` or `openai` for real calls |
| `BLOGAGENT_USE_LLM_EDITOR` | `false` | Set to `true` to enable LLM for research plan, outline, draft, revision |
| `BLOGAGENT_USE_LLM_FACTCHECK` | `false` | Set to `true` to enable LLM for claim extraction and judgment |

If a provider is configured but the API key is missing or the package is not installed,
the system falls back to mock mode with an explicit warning. No crash.

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

Citation matching is deterministic and heuristic:

- No sources → `unsupported`
- Only mock sources → `partially_supported`
- At least one real positive-score source → `supported`

**Semantic claim-to-source matching is not implemented.** The heuristic assigns the same
status to every claim based on the overall source pool. Claims are not individually matched
to the most relevant source unless LLM fact-checking is enabled.

---

## Revision Loop

The revision loop runs at most once (`_MAX_REVISIONS = 1`).

In mock mode, `revise_article` returns the draft unchanged with an explanatory summary —
the revision loop therefore does not improve draft quality without a real LLM. This is
expected: the loop exists to demonstrate the control flow and can be observed by inspecting
`state.revision_summary` and `state.revision_count`.

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

## Not Implemented

- **CMS publishing**: Blocked by the `check_external_effects` guardrail. Any future publishing step requires an explicit user approval gate.
- **Persistence**: `BlogRunState` is in-memory only. No database or file storage is wired up.
- **Streaming**: The pipeline is synchronous and blocking.
- **Async support**: All tools are synchronous.
- **Cost tracking**: No token counting or API cost tracking yet.
- **Browser automation**: Not planned for MVP.
- **Social posting**: Blocked by the external side-effect guardrail.

---

## Recommended Next Steps

1. Set `BLOGAGENT_LLM_PROVIDER=anthropic`, `BLOGAGENT_USE_LLM_EDITOR=true`, `BLOGAGENT_USE_LLM_FACTCHECK=true` and measure eval quality improvement.
2. Add semantic citation matching (replace heuristic with LLM-backed per-claim matching).
3. Add real source grounding checks in evals (count real vs. mock sources, check claim support rates).
4. Implement a persistence layer to store final article packages for review and comparison.
