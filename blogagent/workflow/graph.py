from __future__ import annotations

import os
import time
import uuid

from blogagent.agents import editor_agent
from blogagent.tools.validators import (
    validate_article_package,
    validate_minimum_sources,
    validate_no_unsupported_high_importance_claims,
)
from blogagent.workflow.nodes import (
    build_evidence_table,
    check_external_effects,
    extract_claims,
    extract_webpages,
    generate_outline,
    generate_research_questions,
    intake_topic,
    match_citations,
    package_article,
    run_fact_check,
    run_web_search,
    score_sources,
    write_draft,
)
from blogagent.workflow.state import BlogRunState

_MAX_REVISIONS = 1


def _determine_execution_mode() -> str:
    use_editor = os.getenv("BLOGAGENT_USE_LLM_EDITOR", "false").strip().lower() == "true"
    use_factcheck = os.getenv("BLOGAGENT_USE_LLM_FACTCHECK", "false").strip().lower() == "true"
    use_real_search = os.getenv("BLOGAGENT_SEARCH_PROVIDER", "mock").strip().lower() != "mock"
    any_real = use_editor or use_factcheck or use_real_search
    all_real = use_editor and use_factcheck and use_real_search
    if not any_real:
        return "mock"
    if all_real:
        return "live"
    return "hybrid"


# Deterministic pipeline steps run in order before the fact-check / revision cycle.
# run_fact_check is NOT in this list — it is called explicitly in run_pipeline so
# that tests can monkeypatch blogagent.workflow.graph.run_fact_check cleanly.
_PRE_FACTCHECK = [
    intake_topic,
    check_external_effects,  # guardrail — sets state.blocked; pipeline short-circuits if True
    generate_research_questions,
    run_web_search,
    extract_webpages,
    score_sources,
    build_evidence_table,
    generate_outline,
    write_draft,
    extract_claims,
    match_citations,
]


def run_pipeline(topic: str) -> BlogRunState:
    state = BlogRunState(topic=topic, run_id=str(uuid.uuid4()))
    state.execution_mode = _determine_execution_mode()  # type: ignore[assignment]

    for step in _PRE_FACTCHECK:
        t0 = time.monotonic()
        state = step(state)
        state.stage_timings[step.__name__] = round(time.monotonic() - t0, 3)
        if state.blocked:
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
        revision = editor_agent.revise_article(
            topic=state.topic,
            draft=state.draft,
            fact_check_report=state.fact_check_report,
            citation_matches=state.citation_matches,
        )
        state.stage_timings["revise_article"] = round(time.monotonic() - t0, 3)
        state.draft = revision.revised_markdown
        state.revision_summary = revision.revision_summary
        state.revision_count += 1

        # Re-run claim extraction, citation matching, and fact-check post-revision.
        state = extract_claims(state)
        state = match_citations(state)
        state = run_fact_check(state)

    t0 = time.monotonic()
    state = package_article(state)
    state.stage_timings["package_article"] = round(time.monotonic() - t0, 3)
    return state


def validate_final_state(state: BlogRunState) -> list[str]:
    if state.final_article_package is None:
        return ["final_article_package is None"]
    pkg = state.final_article_package
    errors: list[str] = []
    errors.extend(validate_article_package(pkg))
    errors.extend(validate_minimum_sources(pkg))
    errors.extend(validate_no_unsupported_high_importance_claims(pkg))
    return errors
