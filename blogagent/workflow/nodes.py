from __future__ import annotations

import os
import re
from datetime import datetime, timezone

from blogagent.tools.citation_matcher import CitationMatchInput, citation_matcher
from blogagent.tools.claim_extractor import ClaimExtractInput, claim_extractor
from blogagent.tools.source_score import ScoreInput, source_score
from blogagent.tools.web_search import SearchInput, web_search
from blogagent.tools.webpage_extract import ExtractInput, webpage_extract
from blogagent.workflow.state import (
    ArticlePackage,
    BlogOutline,
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
    state.research_questions = [
        f"What is {state.topic}?",
        f"What are the key facts about {state.topic}?",
        f"What are the latest developments in {state.topic}?",
    ]
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
# Article generation (stubs — replace with LLM calls)
# ---------------------------------------------------------------------------


def generate_outline(state: BlogRunState) -> BlogRunState:
    state.outline = BlogOutline(
        title=f"Understanding {state.topic}",
        sections=["Introduction", "Key Facts", "Recent Developments", "Conclusion"],
        target_word_count=1000,
        seo_keywords=[state.topic],
    )
    return state


def write_draft(state: BlogRunState) -> BlogRunState:
    assert state.outline is not None, "Outline must exist before drafting"
    sections = "\n\n".join(
        f"## {section}\n\n[Placeholder content for {section}.]"
        for section in state.outline.sections
    )
    state.draft = f"# {state.outline.title}\n\n{sections}"
    return state


# ---------------------------------------------------------------------------
# Claim extraction and citation matching (stubs — replace with LLM calls)
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
    matches = state.citation_matches
    supported = sum(1 for m in matches if m.status == CitationStatus.supported)
    partial = sum(1 for m in matches if m.status == CitationStatus.partially_supported)
    unsupported = sum(1 for m in matches if m.status == CitationStatus.unsupported)
    blocking = [
        f"Unsupported high-importance claim: {m.claim.text!r}"
        for m in matches
        if m.status == CitationStatus.unsupported and m.claim.importance == ClaimImportance.high
    ]
    state.fact_check_report = FactCheckReport(
        total_claims=len(matches),
        supported_count=supported,
        partially_supported_count=partial,
        unsupported_count=unsupported,
        matches=matches,
        passed=len(blocking) == 0,
        blocking_issues=blocking,
    )
    return state


def package_article(state: BlogRunState) -> BlogRunState:
    assert state.fact_check_report is not None, "Fact-check must run before packaging"
    assert state.outline is not None, "Outline must exist before packaging"

    title = state.outline.title
    slug = _slugify(title)
    meta_description = f"A comprehensive overview of {state.topic}."
    seo_keywords = list(state.outline.seo_keywords)

    state.final_article_package = ArticlePackage(
        article_markdown=state.draft,
        source_list=state.source_scores,
        fact_check_report=state.fact_check_report,
        claim_support_statuses=state.citation_matches,
        revision_summary="No revision required in stub run.",
        title=title,
        slug=slug,
        meta_description=meta_description,
        seo_keywords=seo_keywords,
        run_id=state.run_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        topic=state.topic,
    )
    return state
