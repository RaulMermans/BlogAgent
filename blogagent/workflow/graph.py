from __future__ import annotations

import re
import time
import uuid

from blogagent.agents import editor_agent
from blogagent.tools.validators import (
    validate_article_package,
    validate_minimum_sources,
    validate_no_unsupported_high_importance_claims,
)
from blogagent.workflow.nodes import (
    _event,
    _propagate_llm_warnings,
    build_evidence_table,
    check_external_effects,
    check_publish_contract_node,
    compute_publish_ready_status,
    evaluate_evidence_sufficiency_node,
    evaluate_publishability_node,
    evaluate_quality,
    extract_claims,
    extract_webpages,
    final_validate_quality,
    generate_outline,
    generate_research_questions,
    ground_article_recommendations,
    intake_topic,
    match_citations,
    package_article,
    revise_if_final_validation_failed,
    revise_if_needed,
    run_editorial_polish,
    run_enrichment_search,
    run_fact_check,
    run_web_search,
    score_source_quality,
    score_sources,
    select_skills,
    write_draft,
)
from blogagent.workflow.state import BlogRunState

_MAX_REVISIONS = 1


def _compute_execution_mode(state: BlogRunState) -> str:
    """Derive execution_mode from what providers actually ran.

    Rules:
      mock   — all actual_provider values are "mock" (no live provider succeeded)
      hybrid — at least one live provider succeeded AND at least one stage used mock
      live   — every stage that ran used a live provider; no mock fallback

    This is computed after the pipeline runs, not from env vars, so it reflects
    what actually happened rather than what was configured.
    """
    live_actual = False
    mock_actual = False

    for event in state.provider_events:
        if "actual_provider=" in event:
            # LLM stage event: "editor.research_plan: ... actual_provider=X ..."
            if "actual_provider=mock" in event:
                mock_actual = True
            else:
                live_actual = True
        elif event.startswith("search:"):
            # Search event: "search: provider=X, results=N"
            if "provider=mock" in event:
                mock_actual = True
            else:
                live_actual = True

    if not live_actual:
        return "mock"
    if mock_actual:
        return "hybrid"
    return "live"


# Deterministic pipeline steps run in order before the fact-check / revision cycle.
# run_fact_check is NOT in this list — it is called explicitly in run_pipeline so
# that tests can monkeypatch blogagent.workflow.graph.run_fact_check cleanly.
_PRE_FACTCHECK = [
    intake_topic,
    check_external_effects,  # guardrail — sets state.blocked; short-circuits if True
    select_skills,  # deterministic skill selection based on intent
    generate_research_questions,
    run_web_search,
    extract_webpages,
    score_sources,
    score_source_quality,  # classify sources as high/medium/low
    build_evidence_table,
    evaluate_evidence_sufficiency_node,  # pre-draft evidence gate
    run_enrichment_search,  # optional second Tavily pass for recommendation topics
    generate_outline,
    write_draft,
    evaluate_quality,  # deterministic quality checks on draft
    revise_if_needed,  # quality-driven revision (at most once)
    final_validate_quality,  # post-revision quality gate
    revise_if_final_validation_failed,  # safety net: final validator can trigger one revision
    extract_claims,
    match_citations,
]


def run_pipeline(topic: str) -> BlogRunState:
    state = BlogRunState(topic=topic, run_id=str(uuid.uuid4()))
    # execution_mode starts as "mock" and is updated after the pipeline finishes.

    for step in _PRE_FACTCHECK:
        t0 = time.monotonic()
        state = step(state)
        state.stage_timings[step.__name__] = round(time.monotonic() - t0, 3)
        if state.blocked:
            state.execution_mode = _compute_execution_mode(state)  # type: ignore[assignment]
            state.run_trace = [f"✗ Blocked: {state.block_reason[:120]}"]
            return state

    # Initial fact-check.
    t0 = time.monotonic()
    state = run_fact_check(state)
    state.stage_timings["run_fact_check"] = round(time.monotonic() - t0, 3)

    # Revision loop — runs at most _MAX_REVISIONS times.
    if (
        state.fact_check_report is not None
        and not state.fact_check_report.passed
        and state.revision_count < _MAX_REVISIONS
    ):
        assert state.outline is not None
        t0 = time.monotonic()
        llm_result = editor_agent.revise_article(
            topic=state.topic,
            draft=state.draft,
            fact_check_report=state.fact_check_report,
            citation_matches=state.citation_matches,
        )
        state.stage_timings["revise_article"] = round(time.monotonic() - t0, 3)
        state.draft = llm_result.data.revised_markdown
        state.revision_summary = llm_result.data.revision_summary
        state.revision_count += 1
        from blogagent.workflow.nodes import _llm_event  # noqa: PLC0415

        _event(state, _llm_event("editor.revision", llm_result))
        _propagate_llm_warnings(state, "editor.revision", llm_result)

        # Re-run claim extraction, citation matching, and fact-check post-revision.
        state = extract_claims(state)
        state = match_citations(state)
        state = run_fact_check(state)

    # Publishability evaluation — runs after fact-check cycle.
    t0 = time.monotonic()
    state = evaluate_publishability_node(state)
    state.stage_timings["evaluate_publishability"] = round(time.monotonic() - t0, 3)

    # Publish contract — deterministic final truth check before polish.
    t0 = time.monotonic()
    state = check_publish_contract_node(state)
    state.stage_timings["check_publish_contract"] = round(time.monotonic() - t0, 3)

    # Editorial polish — runs at most once, when publishability or contract requires it.
    t0 = time.monotonic()
    state = run_editorial_polish(state)
    state.stage_timings["run_editorial_polish"] = round(time.monotonic() - t0, 3)

    # Post-article recommendation grounding — extracts and matches recommendations from
    # the final (polished) article text to source evidence.  Runs after polish so the
    # grounding proof reflects the final published text, not an intermediate draft.
    t0 = time.monotonic()
    state = ground_article_recommendations(state)
    state.stage_timings["ground_article_recommendations"] = round(time.monotonic() - t0, 3)

    # Re-run contract after polish + grounding to reflect any improvements.
    t0 = time.monotonic()
    state = check_publish_contract_node(state)
    state.stage_timings["check_publish_contract_post_polish"] = round(time.monotonic() - t0, 3)

    t0 = time.monotonic()
    state = package_article(state)
    state.stage_timings["package_article"] = round(time.monotonic() - t0, 3)

    # Compute publish readiness status (uses publish contract as final authority).
    state = compute_publish_ready_status(state)

    # Compute execution_mode from what actually ran.
    state.execution_mode = _compute_execution_mode(state)  # type: ignore[assignment]

    # Build agent run trace for UI display.
    state.run_trace = _build_run_trace(state)

    return state


def _build_run_trace(state: BlogRunState) -> list[str]:
    """Build a human-readable agent run trace from pipeline state."""
    trace: list[str] = []

    # Intent
    if state.is_recommendation:
        intent = "recommendation"
    elif state.is_financial:
        intent = "financial"
    else:
        intent = "factual"
    trace.append(f"✓ Intent: {intent}")

    # Requested count
    if state.requested_count is not None:
        trace.append(f"✓ Requested count: {state.requested_count}")

    # Skills
    if state.selected_skills:
        trace.append(f"✓ Skills: {', '.join(state.selected_skills)}")

    # Search
    search_event = next((e for e in state.provider_events if e.startswith("search:")), None)
    if search_event:
        trace.append(f"✓ {search_event}")

    # Source quality
    if state.source_quality_scores:
        high = sum(1 for s in state.source_quality_scores if s.get("quality") == "high")
        medium = sum(1 for s in state.source_quality_scores if s.get("quality") == "medium")
        low = sum(1 for s in state.source_quality_scores if s.get("quality") == "low")
        trace.append(f"✓ Source quality: {high} high, {medium} medium, {low} low")

    # Draft provider
    draft_event = next((e for e in state.provider_events if "editor.draft" in e), None)
    if draft_event:
        m = re.search(r"actual_provider=(\S+)", draft_event)
        provider_name = m.group(1) if m else "unknown"
        is_fallback = "fallback=true" in draft_event
        if is_fallback:
            trace.append("⚠ Draft fallback: mock (live provider unavailable)")
        else:
            completed_fields = "structured_output_completed_missing_fields" in draft_event
            note = " (metadata synthesised from article)" if completed_fields else ""
            trace.append(f"✓ Draft: {provider_name}{note}")

    # Quality evaluation
    if state.quality_evaluation:
        ev = state.quality_evaluation
        symbol = "✓" if ev.get("passes") else "⚠"
        defect_count = len(ev.get("defects", []))
        top_n_defects = [d for d in ev.get("defects", []) if d.get("type") == "top_n_mismatch"]
        detail = ""
        if top_n_defects:
            detail = ", top-N mismatch"
        elif defect_count:
            detail = f", {defect_count} defect(s)"
        trace.append(
            f"{symbol} Quality evaluator: score={ev.get('score', 0)}/100 "
            f"{'passed' if ev.get('passes') else 'failed'}{detail}"
        )

    # Revision — match only actual revision event prefixes, not quality_eval events
    # that happen to contain "revision" (e.g. "revision_required=False").
    revision_events = [
        e
        for e in state.provider_events
        if (
            "editor.quality_revision:" in e
            or "editor.revision:" in e
            or "editor.final_validation_revision:" in e
        )
    ]

    if revision_events:
        last_rev = revision_events[-1]
        m_rev = re.search(r"actual_provider=(\S+)", last_rev)
        rev_provider = m_rev.group(1) if m_rev else "mock"
        summary = (state.revision_summary or "").lower()

        if "editor.final_validation_revision:" in last_rev:
            rev_trigger = "triggered by final validator"
        else:
            rev_trigger = "triggered by quality evaluator"

        evidence_keywords = ("limit", "support", "count")
        if "evidence" in summary and any(k in summary for k in evidence_keywords):
            trace.append(
                f"✓ Revision: completed — reduced count due to evidence limits ({rev_trigger})"
            )
        elif any(kw in summary for kw in ("top_n", "top-n", "count", "recommendation")):
            trace.append(f"✓ Revision: completed — fixed top-N mismatch ({rev_trigger})")
        else:
            trace.append(f"✓ Revision: completed ({rev_provider}, {rev_trigger})")

        if state.final_validation_status == "failed":
            trace.append("⚠ Revision: completed but final validation still found unresolved issues")
    elif state.revision_count == 0:
        qe = state.quality_evaluation or {}
        if qe.get("revision_required"):
            trace.append("⚠ Revision: skipped — revision limit already reached")
        else:
            trace.append(
                "✓ Revision: skipped — quality evaluator passed and final validation passed"
            )
    else:
        # revision_count > 0 but no matching event (edge case)
        trace.append(f"✓ Revision: completed (x{state.revision_count})")

    # Final validation
    fv_status = state.final_validation_status or "passed"
    if fv_status == "failed":
        high_defects = [d for d in state.final_validation_defects if d.get("severity") == "high"]
        defect_msgs = "; ".join(d.get("type", "?") for d in high_defects[:2])
        trace.append(f"⚠ Final validation: failed — {defect_msgs or 'high-severity issues remain'}")
        trace.append("⚠ Generated with unresolved quality issues.")
    elif fv_status == "passed_with_warnings":
        if state.evidence_limited_count_accepted:
            trace.append("⚠ Final validation: passed with evidence-limited count")
        else:
            trace.append("⚠ Final validation: passed with warnings")
    else:
        trace.append("✓ Final validation: passed")

    # Recommendation grounding (post-article)
    if state.is_recommendation and state.recommendation_candidates_summary:
        cs = state.recommendation_candidates_summary
        article_count = cs.get("article_recommendations_count")
        grounded_count = cs.get("grounded_recommendations_count")
        usable = cs.get("usable_count", 0)
        unmatched = cs.get("unmatched_names", [])
        requested = state.requested_count

        if article_count is not None:
            # Post-article grounding data is available
            if grounded_count == article_count and article_count > 0:
                trace.append(
                    f"✓ Article recommendations: {article_count} detected, "
                    f"{grounded_count} grounded in source evidence"
                )
            elif article_count > 0:
                trace.append(
                    f"⚠ Article recommendations: {article_count} detected, "
                    f"{grounded_count} grounded, {len(unmatched)} unsupported"
                )
                if unmatched:
                    trace.append(f"⚠ Unsupported recommendations: {', '.join(unmatched[:3])}")
            else:
                trace.append("⚠ Article recommendations: none detected in final article")

            if requested is not None:
                symbol = "✓" if usable >= requested else "⚠"
                trace.append(f"{symbol} Usable recommendations: {usable}/{requested}")
        else:
            # Only pre-draft evidence candidates available
            if requested is not None:
                symbol = "✓" if usable >= requested else "⚠"
                trace.append(f"{symbol} Usable recommendations (evidence): {usable}/{requested}")
            else:
                trace.append(f"✓ Usable recommendations (evidence): {usable}")

    # Evidence sufficiency
    if state.evidence_sufficiency:
        es = state.evidence_sufficiency
        action = es.get("recommended_action", "proceed")
        supported = es.get("supported_count", 0)
        requested = es.get("requested_count")
        if action == "evidence_limited":
            trace.append(
                f"⚠ Evidence sufficiency: limited, {supported}"
                + (f"/{requested}" if requested else "")
                + " usable recommendations"
            )
        elif action == "search_more" or state.search_pass_count > 1:
            trace.append(
                f"✓ Evidence sufficiency: enriched — {supported}"
                + (f"/{requested}" if requested else "")
                + " usable recommendations"
            )
        else:
            trace.append(f"✓ Evidence sufficiency: {es.get('score', 0)}/100")

    # Enrichment search
    if state.search_pass_count > 1:
        enrichment_event = next(
            (e for e in state.provider_events if e.startswith("enrichment_search:")), None
        )
        if enrichment_event:
            import re as _re  # noqa: PLC0415

            m = _re.search(r"new_sources=(\d+)", enrichment_event)
            new_srcs = m.group(1) if m else "?"
            trace.append(
                f"✓ Enrichment search: {len(state.enrichment_queries)} queries, +{new_srcs} sources"
            )

    # Publishability evaluation
    if state.publishability_evaluation:
        pe = state.publishability_evaluation
        score = pe.get("score", 0)
        polish = pe.get("polish_required", False)
        symbol = "✓" if pe.get("publish_ready") else "⚠"
        trace.append(
            f"{symbol} Publishability: {score}/100" + (", polish needed" if polish else "")
        )

    # Publish contract
    if state.publish_contract:
        pc = state.publish_contract
        contract_status = pc.get("status", "")
        n_defects = len(pc.get("defects", []))
        score_cap = pc.get("score_cap")
        cap_note = f" (score capped at {score_cap})" if score_cap else ""
        if contract_status == "publish_ready":
            trace.append(f"✓ Publish contract: passed{cap_note}")
        elif contract_status == "publish_ready_with_warnings":
            trace.append(
                f"⚠ Publish contract: publish_ready_with_warnings — {n_defects} issue(s){cap_note}"
            )
        else:
            trace.append(
                f"⚠ Publish contract: draft_only_not_publish_ready — {n_defects} issue(s){cap_note}"
            )

    # Editorial polish
    if state.polish_summary:
        trace.append("✓ Editorial polish: completed")
    elif state.publishability_evaluation and state.publishability_evaluation.get("polish_required"):
        trace.append("⚠ Editorial polish: skipped (mock mode — no LLM configured)")

    # Final publish status
    pub_status = state.publish_ready_status
    if pub_status == "publish_ready":
        trace.append("✓ Final status: publish_ready")
    elif pub_status == "publish_ready_with_warnings":
        trace.append("⚠ Final status: publish_ready_with_warnings")
    elif pub_status == "draft_only_not_publish_ready":
        trace.append("⚠ Final status: draft_only_not_publish_ready")

    # Packaged
    trace.append("✓ Packaged article")

    return trace


def validate_final_state(state: BlogRunState) -> list[str]:
    if state.final_article_package is None:
        return ["final_article_package is None"]
    pkg = state.final_article_package
    errors: list[str] = []
    errors.extend(validate_article_package(pkg))
    errors.extend(validate_minimum_sources(pkg))
    errors.extend(validate_no_unsupported_high_importance_claims(pkg))
    return errors
