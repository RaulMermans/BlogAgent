from __future__ import annotations

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

    for step in _PRE_FACTCHECK:
        state = step(state)
        if state.blocked:
            return state

    # Initial fact-check.
    state = run_fact_check(state)

    # Revision loop — runs at most _MAX_REVISIONS times.
    if (
        state.fact_check_report is not None
        and not state.fact_check_report.passed
        and state.revision_count < _MAX_REVISIONS
    ):
        assert state.outline is not None
        revision = editor_agent.revise_article(
            topic=state.topic,
            draft=state.draft,
            fact_check_report=state.fact_check_report,
            citation_matches=state.citation_matches,
        )
        state.draft = revision.revised_markdown
        state.revision_summary = revision.revision_summary
        state.revision_count += 1

        # Re-run claim extraction, citation matching, and fact-check post-revision.
        state = extract_claims(state)
        state = match_citations(state)
        state = run_fact_check(state)

    state = package_article(state)
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
