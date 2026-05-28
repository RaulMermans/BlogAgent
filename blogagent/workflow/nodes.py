from __future__ import annotations

import os
import re
from datetime import datetime, timezone

from blogagent.agents import editor_agent, fact_check_evaluator
from blogagent.llm.client import detect_repeated_excerpts
from blogagent.llm.schemas import LLMResult
from blogagent.tools.citation_matcher import CitationMatchInput, citation_matcher
from blogagent.tools.claim_extractor import ClaimExtractInput, claim_extractor
from blogagent.tools.source_score import ScoreInput, source_score
from blogagent.tools.web_search import SearchInput, web_search
from blogagent.tools.webpage_extract import ExtractInput, webpage_extract
from blogagent.workflow.recommendation import (
    FINANCIAL_DISCLAIMER_WARNING,
    MOCK_RECOMMENDATION_WARNING,
    extract_requested_count,
    is_financial_topic,
    is_real_search_active,
    is_recommendation_topic,
)
from blogagent.workflow.state import (
    ArticlePackage,
    BlogRunState,
    CitationStatus,
    ClaimImportance,
    EvidenceItem,
    FactCheckReport,
)

_DEFAULT_MAX_RESULTS = 5


# ---------------------------------------------------------------------------
# Trace helpers
# ---------------------------------------------------------------------------


def _event(state: BlogRunState, msg: str) -> None:
    state.provider_events.append(msg)


def _warn(state: BlogRunState, msg: str) -> None:
    state.warnings.append(msg)


def _llm_event(stage: str, result: LLMResult) -> str:
    """Format a provider event string from an LLMResult.

    Format: <stage>: configured_provider=X actual_provider=Y model=Z fallback=bool [warning="..."]
    """
    configured = result.configured_provider or "mock"
    actual = result.provider
    model = result.model
    fallback = result.is_mock and configured != "mock"
    parts = [
        f"{stage}:",
        f"configured_provider={configured}",
        f"actual_provider={actual}",
        f"model={model}",
        f"fallback={str(fallback).lower()}",
    ]
    if result.warning:
        parts.append(f'warning="{result.warning}"')
    return " ".join(parts)


def _propagate_llm_warnings(state: BlogRunState, stage: str, result: LLMResult) -> None:
    """Append fallback warnings from an LLMResult to state.warnings."""
    configured = result.configured_provider or "mock"
    if result.warning and configured != "mock":
        _warn(state, f"{stage} fallback: {result.warning}")
    if result.error:
        _warn(state, f"{stage} error: {result.error}")


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
    """Block topics that request external side effects; detect recommendation/financial intent."""
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

    # Detect recommendation and financial intent (deterministic, no LLM).
    state.is_recommendation = is_recommendation_topic(state.topic)
    state.is_financial = is_financial_topic(state.topic)

    # Extract explicit item count from topic (e.g. "top 10" → 10).
    state.requested_count = extract_requested_count(state.topic)

    # Mock-search guardrail: recommendation topics need real sources to produce
    # named-product lists.  We produce a limited response (not a full block) so
    # schema validation still passes, but we surface a clear warning.
    if state.is_recommendation and not is_real_search_active():
        _warn(state, MOCK_RECOMMENDATION_WARNING)

    # Financial disclaimer: always add for investment/trading topics.
    if state.is_financial:
        _warn(state, FINANCIAL_DISCLAIMER_WARNING)

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
    from blogagent.skills.registry import get_skill_briefs  # noqa: PLC0415

    result = editor_agent.generate_research_plan(
        topic=state.topic,
        is_recommendation=state.is_recommendation,
        skill_briefs=get_skill_briefs(state.selected_skills),
    )
    state.research_questions = result.data.research_questions
    _event(state, _llm_event("editor.research_plan", result))
    _propagate_llm_warnings(state, "editor.research_plan", result)
    return state


def run_web_search(state: BlogRunState) -> BlogRunState:
    max_results = int(os.getenv("BLOGAGENT_MAX_SEARCH_RESULTS", str(_DEFAULT_MAX_RESULTS)))
    output = web_search(SearchInput(query=state.topic, max_results=max_results))
    state.search_results = output.results
    _event(state, f"search: provider={output.provider}, results={len(output.results)}")
    if output.warning:
        _warn(state, f"search fallback: {output.warning}")
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
    """Build the evidence table, using real extracted text or snippets when available."""
    # Build lookup maps so we can attach real content to each scored source.
    packet_map = {p.url: p for p in state.selected_sources}
    search_map = {r.url: r for r in state.search_results}

    evidence_items: list[EvidenceItem] = []
    for s in state.source_scores:
        packet = packet_map.get(s.url)
        result = search_map.get(s.url)

        # Prefer real extracted text, then search snippet, then generic fallback.
        if packet and not packet.is_mock and packet.extracted_text.strip():
            fact = packet.extracted_text[:400].strip()
        elif result and not result.is_mock and result.snippet.strip():
            fact = result.snippet.strip()
        else:
            fact = f"Information about {state.topic} from {s.title}"

        evidence_items.append(
            EvidenceItem(
                fact=fact,
                source_url=s.url,
                source_title=s.title,
                publisher_domain=s.domain,
                confidence=s.overall_score,
                used_for="background",
            )
        )

    state.evidence_table = evidence_items
    return state


# ---------------------------------------------------------------------------
# Article generation — backed by Editor Agent
# ---------------------------------------------------------------------------


def generate_outline(state: BlogRunState) -> BlogRunState:
    """Call the Editor Agent to produce an evidence-grounded outline."""
    from blogagent.skills.registry import get_skill_briefs  # noqa: PLC0415

    result = editor_agent.generate_outline(
        topic=state.topic,
        evidence_table=state.evidence_table,
        source_scores=state.source_scores,
        is_recommendation=state.is_recommendation,
        skill_briefs=get_skill_briefs(state.selected_skills),
    )
    from blogagent.workflow.state import BlogOutline  # noqa: PLC0415

    state.outline = BlogOutline(
        title=result.data.title,
        sections=result.data.sections,
        target_word_count=result.data.target_word_count,
        seo_keywords=result.data.seo_keywords,
    )
    _event(state, _llm_event("editor.outline", result))
    _propagate_llm_warnings(state, "editor.outline", result)
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
    from blogagent.skills.registry import get_skill_briefs  # noqa: PLC0415

    result = editor_agent.write_article_draft(
        topic=state.topic,
        outline=outline_out,
        evidence_table=state.evidence_table,
        source_scores=state.source_scores,
        is_recommendation=state.is_recommendation,
        is_financial=state.is_financial,
        skill_briefs=get_skill_briefs(state.selected_skills),
    )
    state.draft = result.data.article_markdown
    state.draft_meta_description = result.data.meta_description
    state.draft_seo_keywords = result.data.seo_keywords
    _event(state, _llm_event("editor.draft", result))
    _propagate_llm_warnings(state, "editor.draft", result)

    # Repeated-text guardrail — warn if the same excerpt appears in 3+ sections.
    for w in detect_repeated_excerpts(state.draft):
        _warn(state, f"repeated-text: {w}")

    return state


# ---------------------------------------------------------------------------
# Claim extraction and citation matching
# ---------------------------------------------------------------------------


def extract_claims(state: BlogRunState) -> BlogRunState:
    output = claim_extractor(ClaimExtractInput(draft=state.draft, topic=state.topic))
    state.claims = output.claims
    return state


def match_citations(state: BlogRunState) -> BlogRunState:
    output = citation_matcher(
        CitationMatchInput(
            claims=state.claims,
            sources=state.source_scores,
            source_packets=state.selected_sources,
        )
    )
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

    use_llm_factcheck = (
        os.getenv("BLOGAGENT_USE_LLM_FACTCHECK", "false").strip().lower() == "true"
    )

    if use_llm_factcheck:
        llm_result = fact_check_evaluator.evaluate_draft(
            topic=state.topic,
            draft=state.draft,
            claims=state.claims,
            citation_matches=state.citation_matches,
            source_scores=state.source_scores,
        )
        judgment = llm_result.data
        _event(state, _llm_event("fact_check", llm_result))
        _propagate_llm_warnings(state, "fact_check", llm_result)

        if judgment is not None:
            all_blocking = list(dict.fromkeys(blocking + judgment.blocking_issues))
        else:
            all_blocking = blocking
    else:
        all_blocking = blocking
        _event(
            state,
            "fact_check: configured_provider=mock actual_provider=mock "
            "model=mock-1.0 fallback=false",
        )

    passed = len(all_blocking) == 0

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


# ---------------------------------------------------------------------------
# Skill selection
# ---------------------------------------------------------------------------


def select_skills(state: BlogRunState) -> BlogRunState:
    """Deterministically select editorial skills based on topic intent."""
    from blogagent.skills.loader import select_skills as _select_skills  # noqa: PLC0415

    state.selected_skills = _select_skills(
        topic=state.topic,
        is_recommendation=state.is_recommendation,
        is_financial=state.is_financial,
    )
    _event(state, f"skills: selected={','.join(state.selected_skills)}")
    return state


# ---------------------------------------------------------------------------
# Source quality classification
# ---------------------------------------------------------------------------


def score_source_quality(state: BlogRunState) -> BlogRunState:
    """Classify each scored source as high / medium / low quality."""
    from blogagent.tools.source_quality import classify_source_quality  # noqa: PLC0415

    state.source_quality_scores = [
        classify_source_quality(s).model_dump() for s in state.source_scores
    ]
    return state


# ---------------------------------------------------------------------------
# Quality evaluation
# ---------------------------------------------------------------------------


def evaluate_quality(state: BlogRunState) -> BlogRunState:
    """Run deterministic quality checks on the draft."""
    from blogagent.agents.quality_evaluator import (  # noqa: PLC0415
        evaluate_quality as _evaluate,
    )

    result = _evaluate(
        topic=state.topic,
        draft=state.draft,
        evidence_table=state.evidence_table,
        source_scores=state.source_scores,
        source_quality_scores=state.source_quality_scores,
        warnings=list(state.warnings),
        is_recommendation=state.is_recommendation,
        is_financial=state.is_financial,
        requested_count=state.requested_count,
        selected_skills=state.selected_skills,
    )
    state.quality_evaluation = result.model_dump()
    _event(
        state,
        f"quality_eval: score={result.score} passes={result.passes} "
        f"revision_required={result.revision_required} defects={len(result.defects)}",
    )
    return state


# ---------------------------------------------------------------------------
# Quality-driven revision (runs at most once per pipeline)
# ---------------------------------------------------------------------------

_QUALITY_MAX_REVISIONS = 1  # matches _MAX_REVISIONS in graph.py


def revise_if_needed(state: BlogRunState) -> BlogRunState:
    """Call the Revision Agent when the quality evaluator requires it."""
    if state.quality_evaluation is None:
        return state
    if not state.quality_evaluation.get("revision_required", False):
        return state
    if state.revision_count >= _QUALITY_MAX_REVISIONS:
        _warn(state, "Quality revision skipped: revision limit reached.")
        return state

    from blogagent.agents.revision_agent import (  # noqa: PLC0415
        revise_with_quality_context,
    )

    llm_result = revise_with_quality_context(
        topic=state.topic,
        draft=state.draft,
        quality_evaluation=state.quality_evaluation,
        warnings=list(state.warnings),
        is_recommendation=state.is_recommendation,
        is_financial=state.is_financial,
        requested_count=state.requested_count,
        selected_skills=state.selected_skills,
        source_quality_scores=state.source_quality_scores,
    )

    state.draft = llm_result.data.revised_markdown
    state.revision_summary = llm_result.data.revision_summary
    state.revision_count += 1
    _event(state, _llm_event("editor.quality_revision", llm_result))
    _propagate_llm_warnings(state, "editor.quality_revision", llm_result)
    return state


# ---------------------------------------------------------------------------
# Final validation (post-revision quality gate — packages with warnings)
# ---------------------------------------------------------------------------


def final_validate_quality(state: BlogRunState) -> BlogRunState:
    """Deterministic final validation after revision.

    Does NOT block factual, low-risk topics unless the article is empty or unsafe.
    Appends warnings for imperfect articles but always allows packaging.
    """
    import re as _re  # noqa: PLC0415

    fin_warns: list[str] = []

    # Empty article is always a hard warning.
    if not state.draft.strip():
        fin_warns.append("Final validation: article_markdown is empty after revision.")

    # Financial disclaimer must survive revision.
    if state.is_financial:
        lower = state.draft.lower()
        has_disclaimer = (
            "not financial advice" in lower
            or "educational purposes only" in lower
            or "consult a qualified financial" in lower
        )
        if not has_disclaimer:
            fin_warns.append(
                "Final validation: financial disclaimer missing after revision."
            )

    # Top-N count re-check post-revision.
    if state.is_recommendation and state.requested_count is not None:
        m = _re.search(
            r"##\s*Quick Picks\s*\n(.*?)(?=\n##|\Z)", state.draft, _re.DOTALL
        )
        actual = len(_re.findall(r"^\s*[-*]\s+.+", m.group(1), _re.MULTILINE)) if m else 0
        if actual != state.requested_count:
            fin_warns.append(
                f"Final validation: top-N count still mismatched "
                f"({actual} vs {state.requested_count} requested)."
            )

    # Repeated-text re-check.
    from blogagent.llm.client import detect_repeated_excerpts  # noqa: PLC0415

    for w in detect_repeated_excerpts(state.draft):
        fin_warns.append(f"Final validation: {w}")

    state.final_validation_warnings = fin_warns
    for w in fin_warns:
        _warn(state, w)

    return state


def package_article(state: BlogRunState) -> BlogRunState:
    assert state.fact_check_report is not None, "Fact-check must run before packaging"
    assert state.outline is not None, "Outline must exist before packaging"

    title = state.outline.title
    slug = _slugify(title)

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
