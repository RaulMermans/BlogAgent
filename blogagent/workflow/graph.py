from __future__ import annotations

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
    evaluate_quality,
    extract_claims,
    extract_webpages,
    final_validate_quality,
    generate_outline,
    generate_research_questions,
    intake_topic,
    match_citations,
    package_article,
    revise_if_needed,
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
    check_external_effects,    # guardrail — sets state.blocked; short-circuits if True
    select_skills,             # deterministic skill selection based on intent
    generate_research_questions,
    run_web_search,
    extract_webpages,
    score_sources,
    score_source_quality,      # classify sources as high/medium/low
    build_evidence_table,
    generate_outline,
    write_draft,
    evaluate_quality,          # deterministic quality checks on draft
    revise_if_needed,          # quality-driven revision (at most once)
    final_validate_quality,    # post-revision quality gate (packages with warnings)
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

    t0 = time.monotonic()
    state = package_article(state)
    state.stage_timings["package_article"] = round(time.monotonic() - t0, 3)

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

    # Skills
    if state.selected_skills:
        trace.append(f"✓ Skills: {', '.join(state.selected_skills)}")

    # Search
    search_event = next(
        (e for e in state.provider_events if e.startswith("search:")), None
    )
    if search_event:
        trace.append(f"✓ {search_event}")

    # Source quality
    if state.source_quality_scores:
        high = sum(1 for s in state.source_quality_scores if s.get("quality") == "high")
        medium = sum(
            1 for s in state.source_quality_scores if s.get("quality") == "medium"
        )
        low = sum(1 for s in state.source_quality_scores if s.get("quality") == "low")
        trace.append(f"✓ Source quality: {high} high, {medium} medium, {low} low")

    # Draft provider
    draft_event = next(
        (e for e in state.provider_events if "editor.draft" in e), None
    )
    if draft_event:
        # Extract just the actual_provider part for readability.
        import re as _re  # noqa: PLC0415

        m = _re.search(r"actual_provider=(\S+)", draft_event)
        provider_name = m.group(1) if m else "unknown"
        trace.append(f"✓ Draft: {provider_name}")

    # Quality evaluation
    if state.quality_evaluation:
        ev = state.quality_evaluation
        symbol = "✓" if ev.get("passes") else "⚠"
        defect_count = len(ev.get("defects", []))
        trace.append(
            f"{symbol} Quality evaluator: score={ev.get('score', 0)}/100 "
            f"{'passed' if ev.get('passes') else 'failed'}"
            f"{f', {defect_count} defect(s)' if defect_count else ''}"
        )

    # Revision
    revision_event = next(
        (e for e in state.provider_events if "revision" in e), None
    )
    if revision_event:
        m2 = _re.search(r"actual_provider=(\S+)", revision_event)
        rev_provider = m2.group(1) if m2 else "unknown"
        trace.append(f"✓ Revision: {rev_provider}")
    elif state.revision_count == 0:
        trace.append("✓ Revision: not required")

    # Final validation
    if state.final_validation_warnings:
        for w in state.final_validation_warnings:
            trace.append(f"⚠ {w}")
        trace.append("⚠ Final validation: passed with warnings")
    else:
        trace.append("✓ Final validation: passed")

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
