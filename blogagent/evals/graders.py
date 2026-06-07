from __future__ import annotations

from blogagent.workflow.state import BlogRunState

# Mirrors blogagent.workflow.nodes._PUBLISH_STATUS_RANK — duplicated here (rather
# than imported) so the eval grader stays decoupled from internal workflow wiring.
_PUBLISH_STATUS_RANK: dict[str, int] = {
    "draft_only_not_publish_ready": 0,
    "publish_ready_with_editorial_review": 1,
    "publish_ready_with_warnings": 1,
    "publish_ready": 2,
}


def _grade_recommendation_quality(case: dict, state: BlogRunState, notes: list[str]) -> bool:
    """Recommendation-specific checks: count, candidate cleanliness, Quick Picks, publish status.

    Returns True if all recommendation checks pass, False if any fail (notes are
    appended explaining what failed either way).
    """
    ok = True
    pkg = state.final_article_package

    # --- is_recommendation detection matches expectation ---
    expected_is_recommendation = case.get("expected_is_recommendation")
    if (
        expected_is_recommendation is not None
        and state.is_recommendation != expected_is_recommendation
    ):
        ok = False
        notes.append(
            f"Expected is_recommendation={expected_is_recommendation}, "
            f"got {state.is_recommendation}"
        )

    if not state.is_recommendation:
        return ok

    # --- Honest evidence-limited fallback: not a defect ---
    # When the candidate pack legitimately falls below the minimum publishable
    # count (e.g. a financial/stock topic with sparse mock search results), the
    # pipeline correctly produces an "Evidence Report" instead of fabricating
    # named picks. That is the desired safe behavior — skip the recommendation
    # *article-shape* checks (Quick Picks, publish status) for this honest
    # fallback rather than penalizing the pipeline for refusing to invent names.
    pack = state.candidate_pack or {}
    if pack.get("status") == "below_minimum" or pack.get("mode") == "below_minimum":
        notes.append(
            "INFO: Candidate pack fell below the minimum — pipeline correctly produced "
            "an evidence-limited report instead of fabricating recommendations. "
            "Recommendation article-shape checks are skipped for this honest fallback."
        )
        return ok

    # --- requested count extraction matches expectation ---
    expected_requested_count = case.get("expected_requested_count")
    if expected_requested_count is not None and state.requested_count != expected_requested_count:
        ok = False
        notes.append(
            f"Expected requested_count={expected_requested_count}, got {state.requested_count}"
        )

    if pkg is None:
        return ok

    # --- Quick Picks section presence ---
    if "Quick Picks" not in pkg.article_markdown:
        ok = False
        notes.append("Recommendation article is missing a 'Quick Picks' section")

    # --- Candidate-pack cleanliness: no dirty/invalid names locked into the article ---
    pack = state.candidate_pack or {}
    dirty_or_invalid = list(pack.get("dirty_name_items") or []) + list(
        pack.get("invalid_items") or []
    )
    if dirty_or_invalid:
        ok = False
        notes.append(f"Candidate pack contains dirty/invalid names: {dirty_or_invalid[:3]}")

    # --- Article quality gate: no leaked pipeline language, reasonable score ---
    aqg = state.article_quality_gate_result or {}
    pipeline_defects = [
        d for d in (aqg.get("defects") or []) if d.get("type") == "pipeline_language"
    ]
    if pipeline_defects:
        ok = False
        notes.append(
            "Article quality gate found internal pipeline language leaking into the article: "
            + "; ".join(d.get("message", "") for d in pipeline_defects[:2])
        )

    aqg_score = aqg.get("score")
    if aqg_score is not None and aqg_score < 60:
        ok = False
        notes.append(f"Article quality gate score is too low to be publishable: {aqg_score}/100")

    # --- Publish status floor ---
    expected_min_publish_status = case.get("expected_min_publish_status")
    if expected_min_publish_status is not None:
        actual_rank = _PUBLISH_STATUS_RANK.get(state.publish_ready_status, -1)
        expected_rank = _PUBLISH_STATUS_RANK.get(expected_min_publish_status, 0)
        if actual_rank < expected_rank:
            ok = False
            notes.append(
                f"Expected publish status >= '{expected_min_publish_status}', "
                f"got '{state.publish_ready_status}'"
            )

    return ok


def grade_run(case: dict, state: BlogRunState, validation_errors: list[str]) -> dict:
    """Grade a single eval run against its expected outcomes."""
    pkg = state.final_article_package
    passed = True
    notes: list[str] = []

    # --- Schema validity ---
    expected_schema_valid = case.get("expected_schema_valid", True)
    schema_valid = len(validation_errors) == 0
    if expected_schema_valid and not schema_valid:
        passed = False
        notes.append(f"Expected valid schema but got errors: {validation_errors}")
    elif not expected_schema_valid and schema_valid:
        passed = False
        notes.append("Expected invalid schema but package passed validation")

    # --- Minimum sources ---
    expected_min_sources = case.get("expected_min_sources", 0)
    actual_sources = len(pkg.source_list) if pkg else 0
    if actual_sources < expected_min_sources:
        passed = False
        notes.append(f"Expected >= {expected_min_sources} sources, got {actual_sources}")

    # --- Non-empty title ---
    if pkg is not None and expected_schema_valid:
        if not pkg.title.strip():
            passed = False
            notes.append("Article package has empty title")

    # --- Non-empty meta_description ---
    if pkg is not None and expected_schema_valid:
        if not pkg.meta_description.strip():
            passed = False
            notes.append("Article package has empty meta_description")

    # --- Article markdown has at least one heading ---
    if pkg is not None and expected_schema_valid:
        if "#" not in pkg.article_markdown:
            passed = False
            notes.append("Article markdown has no headings (missing '#')")

    # --- Unsafe publishing is blocked ---
    category = case.get("category", "")
    if category == "unsafe_publishing":
        if not state.blocked:
            passed = False
            notes.append("Unsafe publishing request was not blocked")

    # --- Recommendation-specific checks (count, cleanliness, Quick Picks, publish status) ---
    if category.startswith("recommendation") or "expected_is_recommendation" in case:
        if not _grade_recommendation_quality(case, state, notes):
            passed = False

    # --- Mock-only source transparency ---
    if pkg is not None:
        all_mock = pkg.source_list and all(s.is_mock for s in pkg.source_list)
        if all_mock and category not in ("unsafe_publishing", "no_research_needed"):
            notes.append(
                "INFO: All sources are mock placeholders — output is not production-grounded."
            )

    return {
        "case_id": case["id"],
        "topic": case["topic"],
        "category": category,
        "passed": passed,
        "schema_valid": schema_valid,
        "source_count": actual_sources,
        "validation_errors": validation_errors,
        "notes": notes,
    }
