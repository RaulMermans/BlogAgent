from __future__ import annotations

import os
import re
import time
from datetime import datetime, timezone

from blogagent.agents import editor_agent, fact_check_evaluator
from blogagent.agents.editorial_polish_agent import (
    EditorialPolishOutput,
    polish_article,
)
from blogagent.agents.evidence_sufficiency import (
    evaluate_evidence_sufficiency,
    generate_enrichment_queries,
)
from blogagent.agents.publish_contract import (
    PublishContractResult,
    check_publish_contract,
)
from blogagent.agents.publishability_evaluator import (
    evaluate_publishability,
)
from blogagent.llm.client import detect_repeated_excerpts
from blogagent.llm.schemas import LLMResult
from blogagent.observability.agentpulse_client import current_client, current_node_id, safe_summary
from blogagent.tools.agent_handoffs import (
    build_polish_handoff,
    build_writer_handoff,
)
from blogagent.tools.article_entity_audit import (
    audit_article_entities,
    build_answer_count_snapshot,
)
from blogagent.tools.candidate_pack import CandidatePack, build_candidate_pack
from blogagent.tools.citation_matcher import CitationMatchInput, citation_matcher
from blogagent.tools.claim_extractor import ClaimExtractInput, claim_extractor
from blogagent.tools.draft_candidate_compliance import (
    check_draft_candidate_compliance,
    derive_recommended_entities_from_markdown,
)
from blogagent.tools.entity_candidate_ledger import build_candidate_ledger
from blogagent.tools.final_answer_contract import build_final_answer_contract
from blogagent.tools.handoff_auditor import (
    audit_polish_output,
    audit_revision_output,
    audit_writer_output,
    build_review_packet,
    build_revision_plan,
)
from blogagent.tools.locked_entity_repair import (
    RepairResult,
    repair_locked_recommendation_article,
)
from blogagent.tools.recommendation_article_skeleton import (
    build_candidate_locked_recommendation_skeleton,
)
from blogagent.tools.source_score import ScoreInput, source_score
from blogagent.tools.tone_profile import resolve_tone_profile
from blogagent.tools.web_search import SearchInput, web_search
from blogagent.tools.webpage_extract import ExtractInput, webpage_extract
from blogagent.workflow.query_contract import (
    QueryContract,
    build_query_contract,
)
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
    client = current_client()
    if client and result.is_mock:
        metadata = {
            "model_provider": result.provider,
            "model_name": result.model,
            "configured_provider": result.configured_provider or "mock",
            "agent": stage,
            "input_tokens": None,
            "output_tokens": None,
            "cost_usd": None,
            "latency_ms": None,
            "is_mock": True,
            "fallback": result.configured_provider != "mock",
            "warning": result.warning,
            "error": result.error,
        }
        client.model_call_started(current_node_id(), metadata)
        if result.error:
            client.model_call_failed(current_node_id(), metadata)
        else:
            client.model_call_completed(current_node_id(), metadata)

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


def build_query_contract_node(state: BlogRunState) -> BlogRunState:
    """Build the query contract after deterministic intent detection."""
    contract = build_query_contract(
        state.topic,
        is_recommendation=state.is_recommendation,
        is_financial=state.is_financial,
        requested_count=state.requested_count,
    )
    state.query_contract = contract.model_dump()
    _event(
        state,
        f"query_contract: {contract.task_type}/{contract.domain}/{contract.answer_entity_type}",
    )
    return state


def resolve_tone_profile_node(state: BlogRunState) -> BlogRunState:
    """Resolve the requested tone or infer a domain default."""
    domain = (state.query_contract or {}).get("domain", "general")
    profile = resolve_tone_profile(state.tone_profile_id, domain)
    state.tone_profile = profile.model_dump()
    _event(state, f"tone_profile: {profile.id}")
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
    client = current_client()
    t0 = time.monotonic()
    if client:
        client.tool_call_started(
            "web_search",
            {
                "permission_class": "read_only",
                "input_summary": safe_summary(state.topic),
                "max_results": max_results,
            },
        )
    try:
        output = web_search(SearchInput(query=state.topic, max_results=max_results))
    except Exception as exc:  # noqa: BLE001
        if client:
            client.tool_call_failed(
                "web_search",
                {
                    "permission_class": "read_only",
                    "error": f"{type(exc).__name__}: {exc}",
                    "latency_ms": int((time.monotonic() - t0) * 1000),
                },
            )
        raise
    if client:
        client.tool_call_completed(
            "web_search",
            {
                "permission_class": "read_only",
                "output_summary": f"{len(output.results)} results from {output.provider}",
                "provider": output.provider,
                "latency_ms": int((time.monotonic() - t0) * 1000),
            },
        )
    state.search_results = output.results
    _event(state, f"search: provider={output.provider}, results={len(output.results)}")
    if output.warning:
        _warn(state, f"search fallback: {output.warning}")
    return state


def extract_webpages(state: BlogRunState) -> BlogRunState:
    packets = []
    client = current_client()
    t0 = time.monotonic()
    if client:
        client.tool_call_started(
            "webpage_extract",
            {
                "permission_class": "read_only",
                "input_summary": f"{len(state.search_results)} URLs",
            },
        )
    for result in state.search_results:
        out = webpage_extract(
            ExtractInput(url=result.url, title=result.title, domain=result.domain)
        )
        if out.packet is not None:
            packets.append(out.packet)
    if client:
        client.tool_call_completed(
            "webpage_extract",
            {
                "permission_class": "read_only",
                "output_summary": f"{len(packets)} source packets",
                "latency_ms": int((time.monotonic() - t0) * 1000),
            },
        )
    state.selected_sources = packets
    return state


def score_sources(state: BlogRunState) -> BlogRunState:
    client = current_client()
    t0 = time.monotonic()
    if client:
        client.tool_call_started(
            "source_score",
            {
                "permission_class": "read_only",
                "input_summary": f"{len(state.selected_sources)} source packets",
            },
        )
    state.source_scores = [
        source_score(ScoreInput(packet=p, topic=state.topic)) for p in state.selected_sources
    ]
    if client:
        client.tool_call_completed(
            "source_score",
            {
                "permission_class": "read_only",
                "output_summary": f"{len(state.source_scores)} source scores",
                "latency_ms": int((time.monotonic() - t0) * 1000),
            },
        )
    return state


def build_evidence_table(state: BlogRunState) -> BlogRunState:
    """Build the evidence table, using real extracted text or snippets when available.

    Also extracts recommendation candidates for recommendation topics.
    """
    from blogagent.tools.recommendation_extractor import (  # noqa: PLC0415
        build_candidates_summary,
        extract_candidates_from_sources,
    )

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

    # Extract recommendation candidates when this is a recommendation topic.
    if state.is_recommendation:
        contract = QueryContract.model_validate(state.query_contract or {})
        candidates = extract_candidates_from_sources(
            sources=state.selected_sources,
            evidence_table=evidence_items,
            query_contract=contract,
            source_quality_scores=state.source_quality_scores,
        )
        state.recommendation_candidates = [c.model_dump() for c in candidates]
        state.validated_candidates = [c.model_dump() for c in candidates if c.usable]
        state.recommendation_candidates_summary = build_candidates_summary(candidates)

        # Build entity candidate ledger for quality analysis
        ledger = build_candidate_ledger(
            sources=state.selected_sources,
            evidence_table=evidence_items,
            query_contract=contract,
            source_quality_scores=state.source_quality_scores,
        )
        state.entity_candidate_ledger = ledger.model_dump()
        state.allowed_candidates = [c.model_dump() for c in ledger.allowed_candidates]
        state.rejected_candidates = [c.model_dump() for c in ledger.rejected_candidates]
        state.candidate_ledger_summary = ledger.to_summary_dict()
        _event(
            state,
            f"candidate_ledger: domain={contract.domain} "
            f"usable={ledger.usable_count} "
            f"rejected={ledger.rejected_count} "
            f"quality={ledger.table_quality}",
        )

        # If the ledger reports "failed", set evidence_limited_mode early
        if ledger.table_quality == "failed":
            state.evidence_limited_mode = True

    return state


# ---------------------------------------------------------------------------
# Structured recommendation handoffs
# ---------------------------------------------------------------------------


def build_candidate_pack_node(state: BlogRunState) -> BlogRunState:
    """Lock the exact recommendation set after bounded research completes."""
    contract = QueryContract.model_validate(state.query_contract or {})
    if state.entity_candidate_ledger is None:
        return state
    pack = build_candidate_pack(contract, state.entity_candidate_ledger)
    state.candidate_pack = pack.model_dump()
    state.evidence_limited_mode = pack.status in {"evidence_limited", "below_minimum"}
    _event(
        state,
        f"candidate_pack: mode={pack.mode} status={pack.status} "
        f"locked={pack.final_target_count} "
        f"allowed={pack.allowed_count} requested={pack.requested_count}",
    )
    return state


def build_writer_handoff_node(state: BlogRunState) -> BlogRunState:
    if not state.candidate_pack:
        return state
    handoff = build_writer_handoff(
        state.query_contract,
        state.candidate_pack,
        state.tone_profile,
    )
    state.writer_handoff = handoff.model_dump()
    return state


def audit_writer_output_node(state: BlogRunState) -> BlogRunState:
    if not state.candidate_pack:
        return state
    audit = audit_writer_output(
        state.draft,
        {"recommended_entities": state.draft_recommended_entities},
        state.candidate_pack,
        state.query_contract,
    )
    state.writer_output_audit = audit.model_dump()
    _event(
        state,
        f"writer_handoff_audit: used={len(audit.used_candidate_ids)}/"
        f"{len(CandidatePack.model_validate(state.candidate_pack).locked_candidate_ids)} "
        f"missing={len(audit.missing_candidate_ids)} "
        f"unknown={len(audit.unknown_candidate_names)}",
    )
    return state


def repair_after_initial_draft(state: BlogRunState) -> BlogRunState:
    return _repair_locked_article(state, stage="initial_draft")


def build_review_packet_node(state: BlogRunState) -> BlogRunState:
    if not state.candidate_pack:
        return state
    current_audit = audit_writer_output(
        state.draft,
        {"recommended_entities": state.draft_recommended_entities},
        state.candidate_pack,
        state.query_contract,
    )
    review = build_review_packet(
        state.draft,
        current_audit,
        state.candidate_pack,
        state.query_contract,
        state.entity_audit,
        state.answer_count_snapshot,
    )
    state.review_packet = review.model_dump()
    _event(
        state,
        f"review_packet: contract_passes={review.contract_passes} "
        f"high_defects={len([d for d in review.defects if d.severity == 'high'])} "
        f"revision_mode={review.required_revision_mode}",
    )
    return state


def build_revision_plan_node(state: BlogRunState) -> BlogRunState:
    if not state.review_packet or not state.candidate_pack:
        return state
    plan = build_revision_plan(state.review_packet, state.candidate_pack)
    state.revision_plan = plan.model_dump()
    return state


def repair_before_final_contract(state: BlogRunState) -> BlogRunState:
    return _repair_locked_article(state, stage="final")


def _repair_locked_article(state: BlogRunState, stage: str) -> BlogRunState:
    if not state.candidate_pack:
        return state
    result = repair_locked_recommendation_article(
        state.draft,
        state.candidate_pack,
        state.query_contract,
    )
    state.draft = result.repaired_markdown
    state.locked_repair_result = _merge_repair_results(
        state.locked_repair_result,
        result,
        stage,
    )
    if result.repair_applied:
        _event(
            state,
            f"locked_repair: stage={stage} restored={len(result.restored_candidate_ids)} "
            f"remaining={len(result.remaining_issues)}",
        )
    return state


def _merge_repair_results(
    existing: dict | None,
    current: RepairResult,
    stage: str,
) -> dict:
    if not existing:
        data = current.model_dump()
        data["repair_summary"] = [f"{stage}: {item}" for item in current.repair_summary]
        return data
    merged = dict(existing)
    merged["repaired_markdown"] = current.repaired_markdown
    merged["repair_applied"] = bool(existing.get("repair_applied")) or current.repair_applied
    merged["restored_candidate_ids"] = list(
        dict.fromkeys(
            list(existing.get("restored_candidate_ids", [])) + list(current.restored_candidate_ids)
        )
    )
    merged["remaining_issues"] = list(current.remaining_issues)
    merged["repair_summary"] = list(existing.get("repair_summary", [])) + [
        f"{stage}: {item}" for item in current.repair_summary
    ]
    return merged


def _candidate_pack_allowed_candidates(state: BlogRunState) -> list[dict]:
    if not state.candidate_pack:
        return list(state.allowed_candidates or state.validated_candidates)
    pack = CandidatePack.model_validate(state.candidate_pack)
    return [
        {
            "candidate_id": item.candidate_id,
            "canonical_name": item.canonical_name,
            "name": item.display_name,
            "raw_mention": item.display_name,
            "entity_type": item.entity_type,
            "entity_subtype": item.entity_subtype,
            "source_urls": [item.source_url] if item.source_url else [],
            "source_titles": [item.source_title] if item.source_title else [],
            "source_quality": item.source_quality or "medium",
            "source_type": item.source_type or "unknown",
            "evidence_spans": list(item.evidence_spans),
            "evidence_terms": list(item.evidence_terms),
            "supported_context": list(item.supported_context),
            "candidate_confidence": item.candidate_confidence,
            "candidate_basis": item.candidate_basis,
            "needs_review": item.needs_review,
            "usable": True,
        }
        for item in pack.items
    ]


# ---------------------------------------------------------------------------
# Article generation — backed by Editor Agent
# ---------------------------------------------------------------------------


def generate_outline(state: BlogRunState) -> BlogRunState:
    """Call the Editor Agent to produce an evidence-grounded outline."""
    from blogagent.skills.registry import get_skill_briefs  # noqa: PLC0415

    locked_skeleton = ""
    if state.candidate_pack:
        locked_skeleton = build_candidate_locked_recommendation_skeleton(
            state.query_contract,
            state.candidate_pack,
            state.topic,
            state.tone_profile,
        )
    result = editor_agent.generate_outline(
        topic=state.topic,
        evidence_table=state.evidence_table,
        source_scores=state.source_scores,
        is_recommendation=state.is_recommendation,
        skill_briefs=get_skill_briefs(state.selected_skills),
        writer_handoff=state.writer_handoff,
        locked_skeleton=locked_skeleton,
        tone_profile=state.tone_profile,
        query_contract=state.query_contract,
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

    # Prefer allowed_candidates from ledger; fall back to validated_candidates
    allowed_recs = _candidate_pack_allowed_candidates(state)
    rejected_recs = state.rejected_candidates or [
        c for c in state.recommendation_candidates if not c.get("usable")
    ]

    locked_skeleton = ""
    if state.candidate_pack:
        locked_skeleton = build_candidate_locked_recommendation_skeleton(
            state.query_contract,
            state.candidate_pack,
            state.topic,
            state.tone_profile,
        )
    result = editor_agent.write_article_draft(
        topic=state.topic,
        outline=outline_out,
        evidence_table=state.evidence_table,
        source_scores=state.source_scores,
        is_recommendation=state.is_recommendation,
        is_financial=state.is_financial,
        skill_briefs=get_skill_briefs(state.selected_skills),
        query_contract=state.query_contract,
        allowed_recommendations=allowed_recs,
        rejected_candidates=rejected_recs,
        evidence_limited_mode=state.evidence_limited_mode,
        source_quality_scores=state.source_quality_scores,
        writer_handoff=state.writer_handoff,
        candidate_pack=state.candidate_pack,
        locked_skeleton=locked_skeleton,
        tone_profile=state.tone_profile,
    )
    state.draft = result.data.article_markdown
    state.draft_meta_description = result.data.meta_description
    state.draft_seo_keywords = result.data.seo_keywords
    recommended_entities = [
        e.model_dump() if hasattr(e, "model_dump") else dict(e)
        for e in (result.data.recommended_entities or [])
    ]
    if state.is_recommendation and not recommended_entities:
        recommended_entities = derive_recommended_entities_from_markdown(
            state.draft,
            allowed_recs,
        )
        if recommended_entities:
            result.data = result.data.model_copy(
                update={"recommended_entities": recommended_entities}
            )
    state.draft_recommended_entities = recommended_entities
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
    client = current_client()
    t0 = time.monotonic()
    if client:
        client.tool_call_started(
            "claim_extractor",
            {
                "permission_class": "read_only",
                "input_summary": f"draft_chars={len(state.draft)}",
            },
        )
    output = claim_extractor(ClaimExtractInput(draft=state.draft, topic=state.topic))
    if client:
        client.tool_call_completed(
            "claim_extractor",
            {
                "permission_class": "read_only",
                "output_summary": f"{len(output.claims)} claims",
                "latency_ms": int((time.monotonic() - t0) * 1000),
            },
        )
    state.claims = output.claims
    return state


def match_citations(state: BlogRunState) -> BlogRunState:
    client = current_client()
    t0 = time.monotonic()
    if client:
        client.tool_call_started(
            "citation_matcher",
            {
                "permission_class": "read_only",
                "input_summary": f"{len(state.claims)} claims; {len(state.source_scores)} sources",
            },
        )
    output = citation_matcher(
        CitationMatchInput(
            claims=state.claims,
            sources=state.source_scores,
            source_packets=state.selected_sources,
        )
    )
    if client:
        client.tool_call_completed(
            "citation_matcher",
            {
                "permission_class": "read_only",
                "output_summary": f"{len(output.matches)} citation matches",
                "latency_ms": int((time.monotonic() - t0) * 1000),
            },
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

    use_llm_factcheck = os.getenv("BLOGAGENT_USE_LLM_FACTCHECK", "false").strip().lower() == "true"

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

    target_count = state.requested_count
    quality_is_recommendation = state.is_recommendation
    if state.candidate_pack:
        pack = CandidatePack.model_validate(state.candidate_pack)
        target_count = pack.final_target_count
        quality_is_recommendation = state.is_recommendation and pack.status != "below_minimum"
    result = _evaluate(
        topic=state.topic,
        draft=state.draft,
        evidence_table=state.evidence_table,
        source_scores=state.source_scores,
        source_quality_scores=state.source_quality_scores,
        warnings=list(state.warnings),
        is_recommendation=quality_is_recommendation,
        is_financial=state.is_financial,
        requested_count=target_count,
        selected_skills=state.selected_skills,
        review_packet=state.review_packet,
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
    review_requires_revision = bool(
        state.review_packet
        and state.review_packet.get("required_revision_mode") in {"targeted_repair", "full_rewrite"}
    )
    if (
        not state.quality_evaluation.get("revision_required", False)
        and not review_requires_revision
    ):
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
        review_packet=state.review_packet,
        revision_plan=state.revision_plan,
        candidate_pack=state.candidate_pack,
        query_contract=state.query_contract,
        tone_profile=state.tone_profile,
    )

    if llm_result.is_mock and llm_result.configured_provider != "mock" and llm_result.error:
        state.revision_status = "failed_structured_output"
        state.revision_summary = "Revision failed structured output; using original draft."
        _event(state, _llm_event("editor.quality_revision", llm_result))
        _propagate_llm_warnings(state, "editor.quality_revision", llm_result)
        return state

    revision_data = llm_result.data
    # Synthesise summary if revised_markdown is present but revision_summary missing
    if revision_data is not None and revision_data.revised_markdown:
        if not revision_data.revision_summary:
            revision_data = revision_data.model_copy(
                update={
                    "revision_summary": (
                        "Revision returned revised_markdown without summary; summary synthesized."
                    )
                }
            )
            llm_result = llm_result.model_copy(
                update={
                    "warning": "structured_output_completed_missing_fields=true",
                    "data": revision_data,
                }
            )

    state.draft = revision_data.revised_markdown
    state.revision_summary = revision_data.revision_summary
    state.revision_status = "completed"
    state.revision_count += 1
    state = _repair_locked_article(state, stage="quality_revision")
    if state.candidate_pack and state.revision_plan:
        audit = audit_revision_output(
            state.draft,
            revision_data,
            state.revision_plan,
            state.candidate_pack,
            state.query_contract,
        )
        state.revision_output_audit = audit.model_dump()
    _event(state, _llm_event("editor.quality_revision", llm_result))
    _propagate_llm_warnings(state, "editor.quality_revision", llm_result)
    return state


# ---------------------------------------------------------------------------
# Final validation (post-revision quality gate — packages with warnings)
# ---------------------------------------------------------------------------


def final_validate_quality(state: BlogRunState) -> BlogRunState:
    """Deterministic final validation after revision.

    Produces structured defects (with severity and fixable flags) in addition
    to the legacy flat warnings list. Sets final_validation_status so the graph
    can decide whether a revision pass is warranted.
    """
    from blogagent.agents.quality_evaluator import (  # noqa: PLC0415
        _is_evidence_limited_article,
        count_recommendations,
    )
    from blogagent.llm.client import detect_repeated_excerpts  # noqa: PLC0415
    from blogagent.tools.recommendation_extractor import (  # noqa: PLC0415
        extract_recommendations_from_article,
    )

    fin_warns: list[str] = []
    defects: list[dict] = []

    # --- Empty article ---
    if not state.draft.strip():
        msg = "Final validation: article_markdown is empty after revision."
        fin_warns.append(msg)
        defects.append(
            {"type": "empty_article", "severity": "high", "message": msg, "fixable": False}
        )

    # --- Financial disclaimer must survive revision ---
    if state.is_financial:
        lower = state.draft.lower()
        has_disclaimer = (
            "not financial advice" in lower
            or "educational purposes only" in lower
            or "consult a qualified financial" in lower
        )
        if not has_disclaimer:
            msg = "Final validation: financial disclaimer missing after revision."
            fin_warns.append(msg)
            defects.append(
                {"type": "missing_disclaimer", "severity": "high", "message": msg, "fixable": True}
            )

    # --- Top-N count re-check post-revision ---
    # Use the rich extractor (not the simple counter) to avoid false "0 vs N" mismatches.
    # extract_recommendations_from_article handles more article formats than count_recommendations.
    evidence_limited = False
    below_minimum = bool(
        state.candidate_pack
        and CandidatePack.model_validate(state.candidate_pack).status == "below_minimum"
    )
    if state.is_recommendation and state.requested_count is not None and not below_minimum:
        # Try rich extractor first; fall back to simple counter
        rich_recs = extract_recommendations_from_article(state.draft)
        actual = len(rich_recs) if rich_recs else count_recommendations(state.draft)
        if actual != state.requested_count:
            evidence_limited = _is_evidence_limited_article(
                state.draft, actual, state.requested_count
            )
            if evidence_limited:
                msg = (
                    f"Final validation: evidence-limited count accepted "
                    f"({actual} vs {state.requested_count} requested). "
                    "Article explains the evidence limitation."
                )
                fin_warns.append(msg)
                defects.append(
                    {"type": "top_n_mismatch", "severity": "low", "message": msg, "fixable": False}
                )
            else:
                # Check if allowed candidates cover the article count
                # (evidenced but not matching requested_count exactly)
                ledger_usable = 0
                if state.entity_candidate_ledger:
                    ledger_usable = state.entity_candidate_ledger.get("usable_count", 0)
                elif state.validated_candidates:
                    ledger_usable = len(state.validated_candidates)

                if (
                    actual > 0
                    and actual >= (state.query_contract or {}).get("minimum_publishable_items", 3)
                    and ledger_usable < state.requested_count
                ):
                    # Ledger has fewer candidates than requested — this is evidence-limited
                    evidence_limited = True
                    msg = (
                        f"Final validation: evidence-limited count ({actual} article "
                        f"recommendations vs {state.requested_count} requested; "
                        f"{ledger_usable} usable candidates found)."
                    )
                    fin_warns.append(msg)
                    defects.append(
                        {
                            "type": "top_n_mismatch",
                            "severity": "low",
                            "message": msg,
                            "fixable": False,
                        }
                    )
                else:
                    msg = (
                        f"Final validation: top-N count still mismatched "
                        f"({actual} vs {state.requested_count} requested)."
                    )
                    fin_warns.append(msg)
                    defects.append(
                        {
                            "type": "top_n_mismatch",
                            "severity": "high",
                            "message": msg,
                            "fixable": True,
                        }
                    )

    # --- Repeated-text re-check ---
    for w in detect_repeated_excerpts(state.draft):
        msg = f"Final validation: {w}"
        fin_warns.append(msg)
        defects.append(
            {"type": "repeated_text", "severity": "medium", "message": msg, "fixable": False}
        )

    state.final_validation_warnings = fin_warns
    state.final_validation_defects = defects
    state.evidence_limited_count_accepted = evidence_limited

    high_defects = [d for d in defects if d["severity"] == "high"]
    if high_defects:
        state.final_validation_status = "failed"
    elif fin_warns:
        state.final_validation_status = "passed_with_warnings"
    else:
        state.final_validation_status = "passed"

    for w in fin_warns:
        _warn(state, w)

    return state


_FINAL_VALIDATION_MAX_REVISIONS = 1  # combined cap with _QUALITY_MAX_REVISIONS


def revise_if_final_validation_failed(state: BlogRunState) -> BlogRunState:
    """Trigger one revision when the final validator catches a high-severity fixable issue.

    Only runs if:
    - final_validation_status == "failed"
    - There is at least one high-severity fixable defect
    - revision_count == 0 (so the total revision cap of 1 is respected)
    """
    if state.revision_count >= _FINAL_VALIDATION_MAX_REVISIONS:
        return state
    if state.final_validation_status != "failed":
        return state

    high_fixable = [
        d
        for d in state.final_validation_defects
        if d.get("severity") == "high" and d.get("fixable", False)
    ]
    if not high_fixable:
        return state

    from blogagent.agents.revision_agent import revise_with_quality_context  # noqa: PLC0415

    synthetic_eval = {
        "passes": False,
        "score": 50,
        "revision_required": True,
        "defects": high_fixable,
        "summary": (
            f"Final validation found {len(high_fixable)} high-severity fixable "
            f"defect(s): {'; '.join(d['type'] for d in high_fixable)}"
        ),
    }

    llm_result = revise_with_quality_context(
        topic=state.topic,
        draft=state.draft,
        quality_evaluation=synthetic_eval,
        warnings=list(state.warnings),
        is_recommendation=state.is_recommendation,
        is_financial=state.is_financial,
        requested_count=state.requested_count,
        selected_skills=state.selected_skills,
        source_quality_scores=state.source_quality_scores,
        review_packet=state.review_packet,
        revision_plan=state.revision_plan,
        candidate_pack=state.candidate_pack,
        query_contract=state.query_contract,
        tone_profile=state.tone_profile,
    )

    if llm_result.is_mock and llm_result.configured_provider != "mock" and llm_result.error:
        state.revision_status = "failed_structured_output"
        state.revision_summary = "Revision failed structured output; using original draft."
        _event(state, _llm_event("editor.final_validation_revision", llm_result))
        _propagate_llm_warnings(state, "editor.final_validation_revision", llm_result)
        return state

    revision_data = llm_result.data
    # Synthesise summary if revised_markdown is present but revision_summary missing
    if revision_data is not None and revision_data.revised_markdown:
        if not revision_data.revision_summary:
            revision_data = revision_data.model_copy(
                update={
                    "revision_summary": (
                        "Revision returned revised_markdown without summary; summary synthesized."
                    )
                }
            )
            llm_result = llm_result.model_copy(
                update={
                    "warning": "structured_output_completed_missing_fields=true",
                    "data": revision_data,
                }
            )

    state.draft = revision_data.revised_markdown
    state.revision_summary = revision_data.revision_summary
    state.revision_status = "completed"
    state.revision_count += 1
    state = _repair_locked_article(state, stage="final_validation_revision")
    if state.candidate_pack and state.revision_plan:
        audit = audit_revision_output(
            state.draft,
            revision_data,
            state.revision_plan,
            state.candidate_pack,
            state.query_contract,
        )
        state.revision_output_audit = audit.model_dump()
    _event(state, _llm_event("editor.final_validation_revision", llm_result))
    _propagate_llm_warnings(state, "editor.final_validation_revision", llm_result)

    # Re-run final validation on the revised draft.
    state = final_validate_quality(state)

    return state


def ground_article_recommendations(state: BlogRunState) -> BlogRunState:
    """Extract recommendations from the final article and match to source evidence.

    Runs after editorial polish so the grounding reflects the final published text.
    Updates recommendation_candidates_summary with article_recommendations_count,
    grounded_recommendations_count, usable_count, and unmatched_names.
    """
    if not state.is_recommendation:
        return state
    if not state.draft or not state.draft.strip():
        return state

    from blogagent.tools.recommendation_extractor import (  # noqa: PLC0415
        audit_article_recommendations,
        build_grounded_candidates_summary,
        extract_recommendations_from_article,
        match_article_recommendations_to_evidence,
    )

    article_recs = extract_recommendations_from_article(state.draft)
    article_count = len(article_recs)

    # Re-hydrate evidence candidates from stored dicts
    evidence_candidates = _candidate_pack_allowed_candidates(state)

    groundings = match_article_recommendations_to_evidence(
        article_recs=article_recs,
        evidence_candidates=evidence_candidates,
        source_quality_scores=state.source_quality_scores,
        evidence_table=state.evidence_table,
        source_scores=state.source_scores,
    )

    # Rebuild the candidates summary with grounding data
    from blogagent.tools.recommendation_extractor import (  # noqa: PLC0415
        RecommendationCandidate,
    )

    # Re-hydrate RecommendationCandidate objects for the summary builder
    cand_objs: list[RecommendationCandidate] = []
    for c in evidence_candidates:
        try:
            cand_objs.append(RecommendationCandidate.model_validate(c))
        except Exception:  # noqa: BLE001
            pass

    state.recommendation_candidates_summary = build_grounded_candidates_summary(
        candidates=cand_objs,
        groundings=groundings,
    )
    contract = QueryContract.model_validate(state.query_contract or {})

    # Use allowed_candidates from ledger when available (more accurate)
    audit_candidates = _candidate_pack_allowed_candidates(state)

    audit = audit_article_recommendations(
        markdown=state.draft,
        allowed_candidates=audit_candidates,
        query_contract=contract,
        evidence_table=state.evidence_table,
        source_quality_scores=state.source_quality_scores,
        source_scores=state.source_scores,
    )
    state.recommendation_audit = audit.model_dump()

    # Build generic EntityAudit
    entity_audit = audit_article_entities(
        article_markdown=state.draft,
        allowed_candidates=audit_candidates,
        query_contract=contract,
        evidence_table=state.evidence_table,
        source_quality_scores=state.source_quality_scores,
        source_scores=state.source_scores,
    )
    state.entity_audit = entity_audit.model_dump()

    # Run draft candidate compliance check
    compliance = check_draft_candidate_compliance(
        article_markdown=state.draft,
        allowed_candidates=audit_candidates,
        query_contract=contract,
        minimum_publishable_items=contract.minimum_publishable_items,
        draft_output={"recommended_entities": state.draft_recommended_entities},
    )
    state.draft_candidate_compliance = compliance.model_dump()

    allowed_count = compliance.allowed_count
    requested = state.requested_count

    if contract.task_type == "recommendation":
        if compliance.passes:
            _event(
                state,
                f"draft_compliance: passes=true "
                f"recommended={compliance.recommended_count} "
                f"allowed_used={compliance.allowed_recommended_count} "
                f"quick_picks={compliance.has_quick_picks}",
            )
        else:
            _warn(state, f"draft_compliance: {compliance.failure_reason}")
            _event(
                state,
                f"draft_compliance: passes=false "
                f"allowed={allowed_count} "
                f"recommended={compliance.recommended_count} "
                f"requested={requested} "
                f"reason={compliance.failure_reason}",
            )

    # Build unified AnswerCountSnapshot — the canonical count for the pipeline
    snapshot = build_answer_count_snapshot(
        requested_count=state.requested_count,
        allowed_candidates=audit_candidates,
        entity_audit=entity_audit,
        query_contract=contract,
        minimum_publishable_items=contract.minimum_publishable_items,
        draft_candidate_compliance=compliance,
    )
    state.answer_count_snapshot = snapshot.model_dump()
    _event(
        state,
        f"answer_count_snapshot: "
        f"requested={snapshot.requested_count} "
        f"allowed={snapshot.allowed_candidates_count} "
        f"article={snapshot.article_entities_count} "
        f"grounded={snapshot.grounded_entities_count} "
        f"compliance={snapshot.draft_candidate_compliance_passes} "
        f"status={snapshot.count_status}",
    )

    grounded_count = state.recommendation_candidates_summary.get(
        "grounded_recommendations_count", 0
    )
    unmatched = state.recommendation_candidates_summary.get("unmatched_names", [])

    if article_count > 0 and grounded_count == article_count:
        _event(
            state,
            f"article_grounding: detected={article_count} grounded={grounded_count} unmatched=0",
        )
    elif article_count > 0:
        _event(
            state,
            f"article_grounding: detected={article_count} grounded={grounded_count} "
            f"unmatched={len(unmatched)}",
        )
    else:
        _event(state, "article_grounding: no recommendations detected in article")

    if audit.passes:
        _event(
            state,
            f"recommendation_audit: article={audit.article_recommendations_count} "
            f"grounded={audit.grounded_recommendations_count} unsupported=0",
        )
    else:
        _event(
            state,
            f"recommendation_audit: article={audit.article_recommendations_count} "
            f"unsupported={len(audit.unsupported_recommendations)} "
            f"brand_only={len(audit.brand_only_recommendations)} "
            f"section_false={len(audit.section_heading_false_positives)}",
        )

    return state


def package_article(state: BlogRunState) -> BlogRunState:
    assert state.fact_check_report is not None, "Fact-check must run before packaging"
    assert state.outline is not None, "Outline must exist before packaging"

    title = state.outline.title
    if state.candidate_pack:
        title_match = re.search(r"^#\s+(.+)$", state.draft, re.MULTILINE)
        if title_match:
            title = title_match.group(1).strip()
    slug = _slugify(title)

    meta_description = state.draft_meta_description or f"A comprehensive overview of {state.topic}."
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


# ---------------------------------------------------------------------------
# Evidence sufficiency evaluation
# ---------------------------------------------------------------------------


def evaluate_evidence_sufficiency_node(state: BlogRunState) -> BlogRunState:
    """Evaluate whether retrieved evidence is sufficient before drafting.

    Uses the entity candidate ledger's usable_count when available,
    which is more accurate than the heuristic proxy.
    """
    enrichment_ran = state.search_pass_count > 1

    # Use ledger usable_count when available — it's the authoritative candidate count
    ledger_candidates: list[dict] | None = None
    if state.is_recommendation and state.entity_candidate_ledger:
        # Build a minimal candidate list matching the expected shape
        ledger_candidates = [
            {"usable": True, "name": n}
            for n in state.entity_candidate_ledger.get("usable_names", [])
        ]
        # Pad with non-usable markers if there are rejected candidates
        rejected_count = state.entity_candidate_ledger.get("rejected_count", 0)
        ledger_candidates.extend([{"usable": False}] * rejected_count)
    elif state.is_recommendation and state.validated_candidates is not None:
        ledger_candidates = state.validated_candidates

    result = evaluate_evidence_sufficiency(
        topic=state.topic,
        requested_count=state.requested_count,
        is_recommendation=state.is_recommendation,
        is_financial=state.is_financial,
        source_quality_scores=state.source_quality_scores,
        evidence_table=state.evidence_table,
        enrichment_already_ran=enrichment_ran,
        recommendation_candidates=ledger_candidates if state.is_recommendation else None,
    )
    state.evidence_sufficiency = result.model_dump()
    state.evidence_limited_mode = result.recommended_action == "evidence_limited"
    _event(
        state,
        f"evidence_sufficiency: sufficient={result.sufficient} score={result.score} "
        f"supported={result.supported_count} requested={result.requested_count} "
        f"action={result.recommended_action}",
    )
    return state


# ---------------------------------------------------------------------------
# Enrichment search (optional second Tavily pass for recommendation topics)
# ---------------------------------------------------------------------------

_MAX_SEARCH_PASSES = 2
_MAX_SOURCES_TOTAL = 10


def run_enrichment_search(state: BlogRunState) -> BlogRunState:
    """Run a targeted second search pass when evidence is insufficient.

    Only triggers when:
    - is_recommendation=True
    - evidence_sufficiency.recommended_action == "search_more"
    - search provider is tavily (real search active)
    - search_pass_count < _MAX_SEARCH_PASSES
    """
    if not state.is_recommendation:
        return state
    if state.search_pass_count >= _MAX_SEARCH_PASSES:
        _warn(state, "Enrichment search skipped: max search passes reached.")
        return state
    if state.evidence_sufficiency is None:
        return state
    if state.evidence_sufficiency.get("recommended_action") != "search_more":
        return state
    if not is_real_search_active():
        _warn(state, "Enrichment search skipped: mock search provider active.")
        return state

    queries = generate_enrichment_queries(
        topic=state.topic,
        missing=state.evidence_sufficiency.get("missing", []),
        requested_count=state.requested_count,
    )
    state.enrichment_queries = queries

    new_results = []
    existing_urls = {r.url for r in state.search_results}

    for query in queries:
        remaining_slots = _MAX_SOURCES_TOTAL - len(state.search_results) - len(new_results)
        if remaining_slots <= 0:
            break
        max_results = min(3, remaining_slots)
        output = web_search(SearchInput(query=query, max_results=max_results))
        for r in output.results:
            if r.url not in existing_urls:
                new_results.append(r)
                existing_urls.add(r.url)
        if output.warning:
            _warn(state, f"enrichment search fallback: {output.warning}")

    if new_results:
        state.search_results = state.search_results + new_results
        state.search_pass_count += 1
        _event(
            state,
            f"enrichment_search: queries={len(queries)} new_sources={len(new_results)} "
            f"total_sources={len(state.search_results)}",
        )

        # Re-extract, re-score, rebuild evidence, and re-evaluate sufficiency
        state = _rebuild_sources_and_evidence(state, existing_result_urls=existing_urls)
        state = evaluate_evidence_sufficiency_node(state)
    else:
        _event(state, "enrichment_search: no new sources found")

    return state


def _rebuild_sources_and_evidence(state: BlogRunState, existing_result_urls: set) -> BlogRunState:
    """Re-run source extraction, scoring, and evidence table after enrichment search."""
    # Only extract pages for newly added results (avoid re-extracting existing ones)
    existing_packet_urls = {p.url for p in state.selected_sources}
    new_results = [r for r in state.search_results if r.url not in existing_packet_urls]

    new_packets = []
    for result in new_results:
        out = webpage_extract(
            ExtractInput(url=result.url, title=result.title, domain=result.domain)
        )
        if out.packet is not None:
            new_packets.append(out.packet)
    state.selected_sources = state.selected_sources + new_packets

    # Re-score all sources (including new ones)
    state.source_scores = [
        source_score(ScoreInput(packet=p, topic=state.topic)) for p in state.selected_sources
    ]

    # Re-classify source quality
    from blogagent.tools.source_quality import classify_source_quality  # noqa: PLC0415

    state.source_quality_scores = [
        classify_source_quality(s).model_dump() for s in state.source_scores
    ]

    # Rebuild evidence table (also re-extracts recommendation candidates)
    state = build_evidence_table(state)
    return state


# ---------------------------------------------------------------------------
# Publishability evaluation
# ---------------------------------------------------------------------------

_POLISH_MAX_COUNT = 1


def evaluate_publishability_node(state: BlogRunState) -> BlogRunState:
    """Run publishability evaluation on the draft."""
    from blogagent.agents.quality_evaluator import count_recommendations  # noqa: PLC0415

    actual_count = count_recommendations(state.draft) if state.is_recommendation else None
    result = evaluate_publishability(
        article_markdown=state.draft,
        topic=state.topic,
        is_recommendation=state.is_recommendation,
        selected_skills=state.selected_skills,
        source_quality_scores=state.source_quality_scores,
        evidence_sufficiency=state.evidence_sufficiency,
        requested_count=state.requested_count,
        actual_recommendation_count=actual_count,
    )
    state.publishability_evaluation = result.model_dump()
    state.publishability_score = result.score
    _event(
        state,
        f"publishability: score={result.score} publish_ready={result.publish_ready} "
        f"polish_required={result.polish_required} defects={len(result.defects)}",
    )
    return state


def _should_run_polish(state: BlogRunState) -> bool:
    """Return True when editorial polish should run."""
    if state.publishability_evaluation is None:
        return False
    pub_eval = state.publishability_evaluation
    if pub_eval.get("polish_required", False):
        return True
    # Also trigger when the publish contract is not publish_ready
    if state.publish_contract and state.publish_contract.get("status") != "publish_ready":
        return True
    return False


def run_editorial_polish(state: BlogRunState) -> BlogRunState:
    """Run editorial polish when publishability or publish contract requires it.

    Runs at most once.
    """
    if not _should_run_polish(state):
        if state.candidate_pack:
            handoff = build_polish_handoff(
                state.draft,
                state.candidate_pack,
                state.tone_profile,
            )
            state.polish_handoff = handoff.model_dump()
            state.polish_output_audit = audit_polish_output(
                state.draft,
                None,
                state.candidate_pack,
                state.query_contract,
            ).model_dump()
        return state

    from blogagent.agents.editor_agent import _format_evidence  # noqa: PLC0415

    evidence_summary = _format_evidence(state.evidence_table, state.source_scores)
    if state.candidate_pack:
        handoff = build_polish_handoff(
            state.draft,
            state.candidate_pack,
            state.tone_profile,
        )
        state.polish_handoff = handoff.model_dump()

    llm_result = polish_article(
        article_markdown=state.draft,
        topic=state.topic,
        publishability_evaluation=state.publishability_evaluation,
        evidence_table_summary=evidence_summary,
        selected_skills=state.selected_skills,
        is_recommendation=state.is_recommendation,
        requested_count=state.requested_count,
        evidence_sufficiency=state.evidence_sufficiency,
        polish_handoff=state.polish_handoff,
        tone_profile=state.tone_profile,
    )

    if llm_result.is_mock and llm_result.configured_provider != "mock" and llm_result.error:
        _event(state, _llm_event("editor.polish", llm_result))
        _propagate_llm_warnings(state, "editor.polish", llm_result)
        _warn(state, "Editorial polish failed structured output; using original draft.")
        return state

    polish_out: EditorialPolishOutput = llm_result.data
    state.draft = polish_out.polished_markdown
    state.polish_summary = list(polish_out.polish_summary)
    if state.candidate_pack:
        polish_audit = audit_polish_output(
            state.draft,
            polish_out,
            state.candidate_pack,
            state.query_contract,
        )
        state.polish_output_audit = polish_audit.model_dump()
        if polish_audit.candidate_list_changed or polish_audit.count_changed:
            state = _repair_locked_article(state, stage="polish")
            remaining = (state.locked_repair_result or {}).get("remaining_issues", [])
            _event(
                state,
                "polish_contract_drift_repaired"
                if not remaining
                else "polish_contract_drift_failed",
            )
    _event(state, _llm_event("editor.polish", llm_result))
    _propagate_llm_warnings(state, "editor.polish", llm_result)

    return state


# ---------------------------------------------------------------------------
# Publish contract check (final truth layer)
# ---------------------------------------------------------------------------


def check_publish_contract_node(state: BlogRunState) -> BlogRunState:
    """Apply the publish contract — the final editorial truth layer."""
    pub_eval = state.publishability_evaluation or {}
    # Pass recommendation grounding data when available (after ground_article_recommendations ran)
    rec_grounding = state.recommendation_candidates_summary if state.is_recommendation else None
    # Use allowed_candidates from ledger when available
    candidates_for_contract = _candidate_pack_allowed_candidates(state)
    result: PublishContractResult = check_publish_contract(
        article_markdown=state.draft,
        topic=state.topic,
        publishability_score=pub_eval.get("score", state.publishability_score),
        publishability_defects=pub_eval.get("defects", []),
        is_recommendation=state.is_recommendation,
        requested_count=state.requested_count,
        evidence_sufficiency=state.evidence_sufficiency,
        source_quality_scores=state.source_quality_scores,
        recommendation_grounding=rec_grounding if rec_grounding else None,
        query_contract=state.query_contract or None,
        validated_candidates=candidates_for_contract,
        recommendation_audit=state.recommendation_audit or None,
        answer_count_snapshot=state.answer_count_snapshot or None,
        draft_candidate_compliance=state.draft_candidate_compliance or None,
        candidate_ledger_summary=state.candidate_ledger_summary or None,
        unsupported_high_importance_claims=(
            list(state.fact_check_report.blocking_issues) if state.fact_check_report else None
        ),
    )
    state.publish_contract = result.model_dump()
    _event(
        state,
        f"publish_contract: status={result.status} passes={result.passes} "
        f"score_cap={result.score_cap} defects={len(result.defects)}",
    )
    return state


# ---------------------------------------------------------------------------
# Final Answer Contract — canonical post-polish count/publish arbiter
# ---------------------------------------------------------------------------


def build_final_answer_contract_node(state: BlogRunState) -> BlogRunState:
    """Build the canonical FinalAnswerContract after all pipeline stages.

    Must run after:
    - editorial polish  (state.draft is final)
    - ground_article_recommendations  (state.answer_count_snapshot is built)
    - check_publish_contract_node (second run, post-polish)
    - package_article  (state.final_article_package.title is available)

    The resulting FinalAnswerContract is then used by compute_publish_ready_status
    as the sole authority on publish_ready_status.
    """
    # Prefer package title; fall back to outline title; fall back to empty
    title = ""
    if state.final_article_package:
        title = state.final_article_package.title
    elif state.outline:
        title = state.outline.title

    meta_description = state.draft_meta_description or ""
    min_publishable = int((state.query_contract or {}).get("minimum_publishable_items") or 3)

    candidate_summary = dict(state.candidate_ledger_summary or {})
    if state.candidate_pack:
        pack = CandidatePack.model_validate(state.candidate_pack)
        candidate_summary["usable_count"] = pack.final_target_count
        candidate_summary["table_quality"] = (
            "failed"
            if pack.status == "below_minimum"
            else "limited"
            if pack.status == "evidence_limited"
            else "strong"
        )
    contract = build_final_answer_contract(
        article_markdown=state.draft,
        title=title,
        meta_description=meta_description,
        answer_count_snapshot=state.answer_count_snapshot or None,
        candidate_ledger_summary=candidate_summary or None,
        query_contract=state.query_contract or None,
        publish_contract=state.publish_contract or None,
        minimum_publishable_items=min_publishable,
        is_recommendation=state.is_recommendation,
        recommendation_audit=state.recommendation_audit or None,
    )
    state.final_answer_contract = contract.model_dump()
    _event(
        state,
        f"final_answer_contract: "
        f"mode={contract.final_count_mode} "
        f"status={contract.publish_status} "
        f"article={contract.final_article_count} "
        f"allowed={contract.allowed_count} "
        f"quick_picks={contract.quick_picks_count} "
        f"title_count={contract.title_declared_count}",
    )
    if contract.failure_reasons:
        for reason in contract.failure_reasons[:2]:
            _warn(state, f"final_answer_contract: {reason}")
    return state


# ---------------------------------------------------------------------------
# Article quality gate (deterministic, runs on the FINAL article)
# ---------------------------------------------------------------------------


_PUBLISH_STATUS_RANK = {
    "draft_only_not_publish_ready": 0,
    "publish_ready_with_editorial_review": 1,
    "publish_ready_with_warnings": 1,
    "publish_ready": 2,
}


def run_article_quality_gate_node(state: BlogRunState) -> BlogRunState:
    """Run the deterministic editorial quality gate on the final article.

    Must run AFTER compute_publish_ready_status — its publish_ceiling acts
    as a hard cap that the computed status cannot exceed. This catches
    issues earlier scoring layers miss: internal pipeline language,
    malformed headings, repeated paragraphs, generic filler intros, and
    (for recommendation articles) missing/duplicate "Best for" entries.
    """
    from blogagent.tools.article_quality_gate import run_article_quality_gate  # noqa: PLC0415

    result = run_article_quality_gate(
        article_markdown=state.draft,
        is_recommendation=state.is_recommendation,
        requested_count=state.requested_count,
        candidate_pack=state.candidate_pack,
    )
    state.article_quality_gate_result = result.model_dump()
    _event(
        state,
        f"article_quality_gate: score={result.score} passes={result.passes} "
        f"ceiling={result.publish_ceiling} defects={len(result.defects)}",
    )
    if not result.passes:
        for defect in result.defects:
            if defect.severity in ("high", "medium"):
                _warn(state, f"article_quality_gate: {defect.message}")

    # Apply the ceiling as a hard cap on the already-computed publish status.
    current = state.publish_ready_status or "draft_only_not_publish_ready"
    current_rank = _PUBLISH_STATUS_RANK.get(current, 0)
    ceiling_rank = _PUBLISH_STATUS_RANK.get(result.publish_ceiling, 2)
    if ceiling_rank < current_rank:
        _warn(
            state,
            f"article_quality_gate: downgraded publish status from {current} "
            f"to {result.publish_ceiling} ({result.summary})",
        )
        state.publish_ready_status = result.publish_ceiling
    return state


# ---------------------------------------------------------------------------
# Publish ready status computation
# ---------------------------------------------------------------------------


def compute_publish_ready_status(state: BlogRunState) -> BlogRunState:
    """Compute the final publish_ready_status after all evaluations.

    Priority order (highest to lowest):
    1. FinalAnswerContract.publish_status — canonical post-polish count arbiter.
       Enforces the invariant that count_status=failed cannot produce
       publish_ready_with_editorial_review, and that title/quick-picks/grounding mismatches
       are caught regardless of what earlier checks reported.
    2. PublishContractResult.status — earlier deterministic hard-fail layer.
    3. Final-validation hard-fail override — if final_validation_status=failed,
       override to draft_only.
    4. Legacy publishability fallback (no contract built).
    """
    fv_status = state.final_validation_status or "passed"

    # 1. FinalAnswerContract is the canonical authority when built.
    if state.final_answer_contract:
        fac_status = state.final_answer_contract.get(
            "publish_status", "draft_only_not_publish_ready"
        )
        # Ensure valid literal
        _VALID_STATUSES = {
            "publish_ready",
            "publish_ready_with_editorial_review",
            "publish_ready_with_warnings",
            "draft_only_not_publish_ready",
        }
        if fac_status not in _VALID_STATUSES:
            fac_status = "draft_only_not_publish_ready"
        # Hard override: if final validation hard-failed, downgrade regardless
        if fv_status == "failed" and fac_status == "publish_ready":
            fac_status = "draft_only_not_publish_ready"
        state.publish_ready_status = fac_status
        return state

    # 2. Fallback: use publish contract.
    if fv_status == "failed":
        state.publish_ready_status = "draft_only_not_publish_ready"
        return state

    if state.publish_contract:
        contract_status = state.publish_contract.get("status", "draft_only_not_publish_ready")
        state.publish_ready_status = contract_status
        return state

    # 3. Legacy fallback (no contract built — should not happen in normal pipeline).
    pub_eval = state.publishability_evaluation
    if pub_eval is None:
        if fv_status == "passed_with_warnings" or state.final_validation_warnings:
            state.publish_ready_status = "publish_ready_with_editorial_review"
        else:
            state.publish_ready_status = "publish_ready"
        return state

    publish_ready = pub_eval.get("publish_ready", False)
    score = pub_eval.get("score", 0)

    if not publish_ready or score < 60:
        state.publish_ready_status = "draft_only_not_publish_ready"
    elif (
        fv_status == "passed_with_warnings"
        or state.final_validation_warnings
        or state.evidence_limited_count_accepted
        or score < 80
    ):
        state.publish_ready_status = "publish_ready_with_editorial_review"
    else:
        state.publish_ready_status = "publish_ready"

    return state
