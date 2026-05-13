# Current Limitations

This document describes what is intentionally not implemented in the current scaffold.

---

## LLM Stubs

All model calls are stubs returning deterministic placeholder data:

| Component | Status | What replaces it |
|---|---|---|
| Editor Agent — research planning | Stub | Claude API call with `RESEARCH_PLAN_PROMPT` |
| Editor Agent — outline generation | Stub | Claude API call with `OUTLINE_PROMPT` |
| Editor Agent — draft writing | Stub | Claude API call with `DRAFT_PROMPT` |
| Editor Agent — revision | Stub | Claude API call with `REVISION_PROMPT` |
| Fact-Check Evaluator — claim extraction | Stub | Claude API call with `FACT_CHECK_PROMPT` |
| `citation_matcher` tool | Stub | LLM-backed semantic matching |

---

## Search and Extraction

| Component | Status | Notes |
|---|---|---|
| `web_search` — mock mode | **Implemented** | Default; returns deterministic mock `SearchResult` objects. `is_mock=True`. |
| `web_search` — Tavily | **Implemented** | Opt-in via `BLOGAGENT_SEARCH_PROVIDER=tavily` + `TAVILY_API_KEY`. Falls back to mock if key missing. |
| `webpage_extract` — mock URLs | **Implemented** | Mock URLs (`*.example.dev`, `*.example.com`) return mock `SourcePacket` without network calls. |
| `webpage_extract` — real URLs | **Implemented** | Uses httpx + BeautifulSoup4. Bounded at 10,000 chars. Graceful error handling. |
| `source_score` | **Implemented** | Fully deterministic; no LLM. Scores domain credibility, keyword overlap, publication year. |

---

## Not Implemented

- **Revision loop**: The pipeline runs once. The evaluator marks blocking issues but the pipeline does not automatically re-enter the Editor Agent for revision. Requires a loop guard with `revision_count` and a `MAX_REVISIONS` constant.
- **CMS publishing**: Blocked by the `check_external_effects` guardrail. Any future publishing step requires an explicit user approval gate.
- **Persistence**: `BlogRunState` is in-memory only. No database or file storage is wired up.
- **Streaming**: The pipeline is synchronous and blocking.
- **Async support**: All tools are synchronous.
- **Cost tracking**: No token counting or API cost tracking yet.
- **Real SEO metadata**: `meta_description` is a stub string. Real generation requires LLM.

---

## Known Placeholder Behaviors

- All sources in mock mode use `*.example.dev` domains — not real URLs.
- All mock source scores are `0.3` — not real credibility assessments.
- All claims are marked `supported` — not real citation matching.
- Draft content is `[Placeholder content for Section]` — not real prose.
- `meta_description` is a template string — not LLM-generated.

These are intentional. The scaffold is meant to be replaced section by section as real tools are connected.

---

## Recommended Next Step

Connect real LLM calls for the Editor Agent (research planning → outline → draft) and the Fact-Check Evaluator (claim extraction → citation matching). The deterministic scaffold, validators, and evals are all in place to measure the quality improvement.
