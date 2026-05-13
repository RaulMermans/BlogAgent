from __future__ import annotations

import os
import re
from datetime import datetime, timezone

from blogagent.agents import editor_agent, fact_check_evaluator
from blogagent.tools.citation_matcher import CitationMatchInput, citation_matcher
from blogagent.tools.claim_extractor import ClaimExtractInput, claim_extractor
from blogagent.tools.source_score import ScoreInput, source_score
from blogagent.tools.web_search import SearchInput, web_search
from blogagent.tools.webpage_extract import ExtractInput, webpage_extract
from blogagent.workflow.state import (
    ArticlePackage,
    BlogRunState,
    CitationStatus,
    ClaimImportance,
    EvidenceItem,
    FactCheckReport,
)

_DEFAULT_MAX_RESULTS = 5

# Phrases that indicate the user wants an external side effect rather than an article.
_BLOCKED_PHRASES = (
    "publish",
    "post to",
    "post this",
    "send to",
    "send this",
    "schedule this",
    "schedule the",
    "upload to",
    "deploy to",
    "submit to",
    "tweet",
    "wordpress",
    "medium.com",
    "substack",
    "email this",
    "email the",
    "push to",
)


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-")


# ---------------------------------------------------------------------------
# Guardrail
# ---------------------------------------------------------------------------


def check_external_effects(state: BlogRunState) -> BlogRunState:
    """Block topics that request external side effects (publishing, posting, etc.)."""
    t = state.topic.lower()
    for phrase in _BLOCKED_PHRASES:
        if phrase in t:
            state.blocked = True
            state.block_reason = (
                f"External side effects are disabled in MVP. "
                f"The topic appears to request an external action (matched: '{phrase}'). "
                f"BlogAgent produces article drafts only; it does not publish externally."
            )
            state.requires_approval = True
            return state
    return state


# ---------------------------------------------------------------------------
# Intake
# ---------------------------------------------------------------------------


def intake_topic(state: BlogRunState) -> BlogRunState:
    state.topic = state.topic.strip()
    return state


# ---------------------------------------------------------------------------
# Research
# ---------------------------------------------------------------------------


def generate_research_questions(state: BlogRunState) -> BlogRunState:
    """Call the Editor Agent to produce research questions."""
    result = editor_agent.generate_research_plan(topic=state.topic)
    state.research_questions = result.research_questions
    return state


def run_web_search(state: BlogRunState) -> BlogRunState:
    max_results = int(os.getenv("BLOGAGENT_MAX_SEARCH_RESULTS", str(_DEFAULT_MAX_RESULTS)))
    output = web_search(SearchInput(query=state.topic, max_results=max_results))
    state.search_results = output.results
    return state


def extract_webpages(state: BlogRunState) -> BlogRunState:
    packets = []
    for result in state.search_results:
        out = webpage_extract(
            ExtractInput(url=result.url, title=result.title, domain=result.domain)
        )
        if out.packet is not None:
            packets.append(out.packet)
    state.selected_sources = packets
    return state


def score_sources(state: BlogRunState) -> BlogRunState:
    state.source_scores = [
        source_score(ScoreInput(packet=p, topic=state.topic)) for p in state.selected_sources
    ]
    return state


def build_evidence_table(state: BlogRunState) -> BlogRunState:
    state.evidence_table = [
        EvidenceItem(
            fact=f"Information about {state.topic} from {s.title}",
            source_url=s.url,
            source_title=s.title,
            publisher_domain=s.domain,
            confidence=s.overall_score,
            used_for="background",
        )
        for s in state.source_scores
    ]
    return state


# ---------------------------------------------------------------------------
# Article generation — backed by Editor Agent
# ---------------------------------------------------------------------------


def generate_outline(state: BlogRunState) -> BlogRunState:
    """Call the Editor Agent to produce an evidence-grounded outline."""
    result = editor_agent.generate_outline(
        topic=state.topic,
        evidence_table=state.evidence_table,
        source_scores=state.source_scores,
    )
    from blogagent.workflow.state import BlogOutline  # noqa: PLC0415

    state.outline = BlogOutline(
        title=result.title,
        sections=result.sections,
        target_word_count=result.target_word_count,
        seo_keywords=result.seo_keywords,
    )
    return state


def write_draft(state: BlogRunState) -> BlogRunState:
    """Call the Editor Agent to write a draft from the outline and evidence."""
    assert state.outline is not None, "Outline must exist before drafting"
    from blogagent.llm.schemas import OutlineOutput  # noqa: PLC0415

    outline_out = OutlineOutput(
        title=state.outline.title,
        sections=state.outline.sections,
        target_word_count=state.outline.target_word_count,
        seo_keywords=state.outline.seo_keywords,
    )
    result = editor_agent.write_article_draft(
        topic=state.topic,
        outline=outline_out,
        evidence_table=state.evidence_table,
        source_scores=state.source_scores,
    )
    state.draft = result.article_markdown
    state.draft_meta_description = result.meta_description
    state.draft_seo_keywords = result.seo_keywords
    return state


# ---------------------------------------------------------------------------
# Claim extraction and citation matching
# ---------------------------------------------------------------------------


def extract_claims(state: BlogRunState) -> BlogRunState:
    output = claim_extractor(ClaimExtractInput(draft=state.draft, topic=state.topic))
    state.claims = output.claims
    return state


def match_citations(state: BlogRunState) -> BlogRunState:
    output = citation_matcher(CitationMatchInput(claims=state.claims, sources=state.source_scores))
    state.citation_matches = output.matches
    return state


# ---------------------------------------------------------------------------
# Fact check and packaging
# ---------------------------------------------------------------------------


def run_fact_check(state: BlogRunState) -> BlogRunState:
    """Assemble the FactCheckReport; optionally supplement with LLM judgment."""
    matches = state.citation_matches
    supported = sum(1 for m in matches if m.status == CitationStatus.supported)
    partial = sum(1 for m in matches if m.status == CitationStatus.partially_supported)
    unsupported = sum(1 for m in matches if m.status == CitationStatus.unsupported)
    blocking = [
        f"Unsupported high-importance claim: {m.claim.text!r}"
        for m in matches
        if m.status == CitationStatus.unsupported and m.claim.importance == ClaimImportance.high
    ]

    import os as _os  # noqa: PLC0415

    if _os.getenv("BLOGAGENT_USE_LLM_FACTCHECK", "false").strip().lower() == "true":
        judgment = fact_check_evaluator.evaluate_draft(
            topic=state.topic,
            draft=state.draft,
            claims=state.claims,
            citation_matches=state.citation_matches,
            source_scores=state.source_scores,
        )
        # Merge LLM blocking issues with deterministic ones (deduplicated).
        all_blocking = list(dict.fromkeys(blocking + judgment.blocking_issues))
        passed = len(all_blocking) == 0
    else:
        all_blocking = blocking
        passed = len(blocking) == 0

    state.fact_check_report = FactCheckReport(
        total_claims=len(matches),
        supported_count=supported,
        partially_supported_count=partial,
        unsupported_count=unsupported,
        matches=matches,
        passed=passed,
        blocking_issues=all_blocking,
    )
    return state


def package_article(state: BlogRunState) -> BlogRunState:
    assert state.fact_check_report is not None, "Fact-check must run before packaging"
    assert state.outline is not None, "Outline must exist before packaging"

    title = state.outline.title
    slug = _slugify(title)

    # Use draft SEO fields when available; fall back to outline/generic.
    meta_description = (
        state.draft_meta_description
        or f"A comprehensive overview of {state.topic}."
    )
    seo_keywords = state.draft_seo_keywords or list(state.outline.seo_keywords)

    revision_summary = state.revision_summary or "No revision performed."

    state.final_article_package = ArticlePackage(
        article_markdown=state.draft,
        source_list=state.source_scores,
        fact_check_report=state.fact_check_report,
        claim_support_statuses=state.citation_matches,
        revision_summary=revision_summary,
        title=title,
        slug=slug,
        meta_description=meta_description,
        seo_keywords=seo_keywords,
        run_id=state.run_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        topic=state.topic,
    )
    return state
