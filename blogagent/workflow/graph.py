from __future__ import annotations

import uuid

from blogagent.workflow.nodes import (
    build_evidence_table,
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
from blogagent.tools.validators import (
    validate_article_package,
    validate_minimum_sources,
    validate_no_unsupported_high_importance_claims,
)

PIPELINE = [
    intake_topic,
    generate_research_questions,
    run_web_search,
    extract_webpages,
    score_sources,
    build_evidence_table,
    generate_outline,
    write_draft,
    extract_claims,
    match_citations,
    run_fact_check,
    package_article,
]


def run_pipeline(topic: str) -> BlogRunState:
    state = BlogRunState(topic=topic, run_id=str(uuid.uuid4()))
    for step in PIPELINE:
        state = step(state)
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
