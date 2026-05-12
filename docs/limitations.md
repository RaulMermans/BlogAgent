# Current Limitations

This document describes what is intentionally not implemented in the current scaffold.

---

## Stub Implementations

The following components are stubs that return deterministic placeholder data:

| Component | Status | What replaces it |
|---|---|---|
| `web_search` tool | Stub | Real search API (e.g. Tavily, Serper, Brave) |
| `webpage_extract` tool | Stub | Real HTTP fetch + text extractor (e.g. Trafilatura) |
| `source_score` tool | Stub | Domain credibility database + LLM relevance scoring |
| Editor Agent — research planning | Stub | Claude API call with `RESEARCH_PLAN_PROMPT` |
| Editor Agent — outline generation | Stub | Claude API call with `OUTLINE_PROMPT` |
| Editor Agent — draft writing | Stub | Claude API call with `DRAFT_PROMPT` |
| Editor Agent — revision | Stub | Claude API call with `REVISION_PROMPT` |
| Fact-Check Evaluator — claim extraction | Stub | Claude API call with `FACT_CHECK_PROMPT` |
| `citation_matcher` tool | Stub | LLM-backed semantic matching |

---

## Not Implemented

- **Revision loop**: The pipeline runs once. The evaluator marks blocking issues but the pipeline does not automatically re-enter the Editor Agent for revision. This requires a loop guard with `revision_count` and a `MAX_REVISIONS` constant.
- **CMS publishing**: Forbidden by CLAUDE.md. No publishing tool exists. Any future publishing step requires an explicit user approval gate.
- **Persistence**: `BlogRunState` is in-memory only. No database or file storage is wired up.
- **Streaming**: The pipeline is synchronous and blocking.
- **Async support**: All tools are synchronous stubs.
- **Cost tracking**: No token counting or API cost tracking yet.
- **SEO metadata generation**: The outline contains `seo_keywords` but no meta description, slug, or structured SEO output is produced.

---

## Known Placeholder Behaviors

- All sources use `example.com`, `example.org`, `example.net` — not real URLs.
- All source scores are `0.7` uniform — not real credibility assessments.
- All claims are marked `supported` — not real citation matching.
- Draft content is `[Placeholder content for Section]` — not real prose.

These are intentional. The scaffold is meant to be replaced section by section as real tools are connected.
