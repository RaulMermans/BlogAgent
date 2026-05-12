from __future__ import annotations

from datetime import datetime, timezone

from blogagent.workflow.state import (
    BlogOutline,
    BlogRunState,
    Claim,
    CitationMatch,
    CitationStatus,
    ClaimImportance,
    EvidenceItem,
    FactCheckReport,
    ArticlePackage,
    SearchResult,
    SourcePacket,
    SourceScore,
)


def intake_topic(state: BlogRunState) -> BlogRunState:
    state.topic = state.topic.strip()
    return state


def generate_research_questions(state: BlogRunState) -> BlogRunState:
    state.research_questions = [
        f"What is {state.topic}?",
        f"What are the key facts about {state.topic}?",
        f"What are the latest developments in {state.topic}?",
    ]
    return state


def run_web_search(state: BlogRunState) -> BlogRunState:
    slug = state.topic.replace(" ", "-").lower()
    state.search_results = [
        SearchResult(
            url=f"https://example.com/{slug}-overview",
            title=f"{state.topic} — Overview",
            snippet=f"An overview of {state.topic}.",
            domain="example.com",
        ),
        SearchResult(
            url=f"https://example.org/{slug}-facts",
            title=f"Key Facts about {state.topic}",
            snippet=f"Key facts about {state.topic}.",
            domain="example.org",
        ),
        SearchResult(
            url=f"https://example.net/{slug}-latest",
            title=f"Latest on {state.topic}",
            snippet=f"The latest developments in {state.topic}.",
            domain="example.net",
        ),
    ]
    return state


def extract_webpages(state: BlogRunState) -> BlogRunState:
    state.selected_sources = [
        SourcePacket(
            url=r.url,
            title=r.title,
            domain=r.domain,
            extracted_text=f"[Stub extracted text for {r.title}]",
            word_count=50,
        )
        for r in state.search_results
    ]
    return state


def score_sources(state: BlogRunState) -> BlogRunState:
    state.source_scores = [
        SourceScore(
            url=s.url,
            title=s.title,
            domain=s.domain,
            credibility_score=0.7,
            relevance_score=0.7,
            recency_score=0.7,
            overall_score=0.7,
            notes="Stub score",
        )
        for s in state.selected_sources
    ]
    return state


def build_evidence_table(state: BlogRunState) -> BlogRunState:
    state.evidence_table = [
        EvidenceItem(
            fact=f"Stub fact from {s.title}",
            source_url=s.url,
            source_title=s.title,
            publisher_domain=s.domain,
            confidence=0.7,
            used_for="background",
        )
        for s in state.source_scores
    ]
    return state


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


def extract_claims(state: BlogRunState) -> BlogRunState:
    state.claims = [
        Claim(
            text=f"{state.topic} is an important subject.",
            importance=ClaimImportance.medium,
            section="Introduction",
        )
    ]
    return state


def match_citations(state: BlogRunState) -> BlogRunState:
    state.citation_matches = [
        CitationMatch(
            claim=claim,
            status=CitationStatus.supported,
            supporting_sources=[s.url for s in state.source_scores[:1]],
            notes="Stub match",
        )
        for claim in state.claims
    ]
    return state


def run_fact_check(state: BlogRunState) -> BlogRunState:
    matches = state.citation_matches
    supported = sum(1 for m in matches if m.status == CitationStatus.supported)
    partial = sum(1 for m in matches if m.status == CitationStatus.partially_supported)
    unsupported = sum(1 for m in matches if m.status == CitationStatus.unsupported)
    blocking = [
        f"Unsupported high-importance claim: {m.claim.text!r}"
        for m in matches
        if m.status == CitationStatus.unsupported
        and m.claim.importance == ClaimImportance.high
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
    state.final_article_package = ArticlePackage(
        article_markdown=state.draft,
        source_list=state.source_scores,
        fact_check_report=state.fact_check_report,
        claim_support_statuses=state.citation_matches,
        revision_summary="No revision required in stub run.",
        run_id=state.run_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        topic=state.topic,
    )
    return state
