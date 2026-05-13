from blogagent.workflow.graph import run_pipeline, validate_final_state
from blogagent.workflow.state import (
    BlogRunState,
)

# ---------------------------------------------------------------------------
# Pipeline basics
# ---------------------------------------------------------------------------


def test_pipeline_returns_state_with_correct_topic():
    state = run_pipeline("Climate Change")
    assert state.topic == "Climate Change"


def test_pipeline_strips_topic_whitespace():
    state = run_pipeline("  Solar Energy  ")
    assert state.topic == "Solar Energy"


def test_pipeline_produces_research_questions():
    state = run_pipeline("The Water Cycle")
    assert len(state.research_questions) >= 1


def test_pipeline_produces_source_scores():
    state = run_pipeline("The History of the Internet")
    assert len(state.source_scores) >= 3


def test_pipeline_produces_evidence_table():
    state = run_pipeline("Renewable Energy")
    assert len(state.evidence_table) >= 1


def test_pipeline_produces_outline():
    state = run_pipeline("Quantum Computing")
    assert state.outline is not None
    assert state.outline.title
    assert len(state.outline.sections) >= 1


def test_pipeline_produces_non_empty_draft():
    state = run_pipeline("The Solar System")
    assert state.draft.strip() != ""


def test_pipeline_produces_article_package():
    state = run_pipeline("The History of Writing")
    assert state.final_article_package is not None
    pkg = state.final_article_package
    assert pkg.article_markdown.strip()
    assert pkg.source_list
    assert pkg.fact_check_report is not None
    assert pkg.revision_summary.strip()
    assert pkg.topic == "The History of Writing"


def test_pipeline_passes_all_validators():
    state = run_pipeline("The Solar System")
    errors = validate_final_state(state)
    assert errors == [], f"Validation errors: {errors}"


def test_validate_final_state_fails_when_package_is_none():
    state = BlogRunState(topic="X")
    errors = validate_final_state(state)
    assert errors != []


def test_pipeline_run_id_is_set():
    state = run_pipeline("Photosynthesis")
    assert state.run_id != ""
    assert state.final_article_package is not None
    assert state.final_article_package.run_id == state.run_id


# ---------------------------------------------------------------------------
# SEO fields
# ---------------------------------------------------------------------------


def test_pipeline_article_package_has_non_empty_title():
    state = run_pipeline("Photosynthesis")
    assert state.final_article_package is not None
    assert state.final_article_package.title != ""


def test_pipeline_article_package_has_non_empty_slug():
    state = run_pipeline("Photosynthesis")
    assert state.final_article_package is not None
    assert state.final_article_package.slug != ""


def test_pipeline_article_package_slug_has_no_spaces():
    state = run_pipeline("The History of Writing")
    assert state.final_article_package is not None
    assert " " not in state.final_article_package.slug


def test_pipeline_article_package_has_seo_keywords():
    state = run_pipeline("Solar Energy")
    assert state.final_article_package is not None
    assert isinstance(state.final_article_package.seo_keywords, list)


# ---------------------------------------------------------------------------
# External side-effect guardrail
# ---------------------------------------------------------------------------


def test_pipeline_blocked_for_post_to_wordpress():
    state = run_pipeline("Post this article to WordPress immediately")
    assert state.blocked is True
    assert state.final_article_package is None
    assert "blocked" in state.block_reason.lower() or "external" in state.block_reason.lower()


def test_pipeline_blocked_for_publish_request():
    state = run_pipeline("Publish my article on Medium now")
    assert state.blocked is True
    assert state.final_article_package is None


def test_pipeline_blocked_sets_requires_approval():
    state = run_pipeline("Tweet this article now")
    assert state.blocked is True
    assert state.requires_approval is True


def test_pipeline_not_blocked_for_normal_topic():
    state = run_pipeline("The water cycle")
    assert state.blocked is False
    assert state.final_article_package is not None


def test_pipeline_not_blocked_for_post_war_history():
    state = run_pipeline("Post-war economic recovery in Europe")
    assert state.blocked is False


def test_blocked_state_fails_validation():
    state = run_pipeline("Post this article to WordPress immediately")
    errors = validate_final_state(state)
    assert errors != [], "Blocked state must fail validation (no final package)"


# ---------------------------------------------------------------------------
# Mock data tracing
# ---------------------------------------------------------------------------


def test_pipeline_search_results_are_mock_in_mock_mode():
    state = run_pipeline("Solar Energy")
    for result in state.search_results:
        assert result.is_mock is True, f"Expected is_mock=True for {result.url}"


def test_pipeline_selected_sources_are_mock_in_mock_mode():
    state = run_pipeline("Solar Energy")
    for source in state.selected_sources:
        assert source.is_mock is True, f"Expected is_mock=True for {source.url}"


# ---------------------------------------------------------------------------
# New assertions: SEO + draft quality + meta description
# ---------------------------------------------------------------------------


def test_pipeline_article_package_has_non_empty_meta_description():
    state = run_pipeline("Photosynthesis")
    assert state.final_article_package is not None
    assert state.final_article_package.meta_description.strip() != ""


def test_pipeline_article_markdown_has_at_least_one_heading():
    state = run_pipeline("The Water Cycle")
    assert state.final_article_package is not None
    assert "#" in state.final_article_package.article_markdown


def test_pipeline_article_package_seo_keywords_is_list():
    state = run_pipeline("Climate Change")
    assert state.final_article_package is not None
    assert isinstance(state.final_article_package.seo_keywords, list)


def test_pipeline_revision_count_is_zero_in_mock_mode():
    """In default mock mode, claims are medium-importance and mock sources give
    partially_supported — so no blocking issues → no revision triggered."""
    state = run_pipeline("The Water Cycle")
    assert state.revision_count == 0


def test_pipeline_revision_count_never_exceeds_one(monkeypatch):
    import blogagent.workflow.graph as _graph
    from blogagent.workflow.state import FactCheckReport

    call_count = [0]
    original = _graph.run_fact_check

    def patched(state):
        call_count[0] += 1
        if call_count[0] == 1:
            state.fact_check_report = FactCheckReport(
                total_claims=1,
                supported_count=0,
                partially_supported_count=0,
                unsupported_count=1,
                passed=False,
                blocking_issues=["Unsupported high-importance claim: 'X'"],
            )
            return state
        return original(state)

    monkeypatch.setattr(_graph, "run_fact_check", patched)
    state = run_pipeline("Climate Change")
    assert state.revision_count <= 1


def test_pipeline_draft_is_no_longer_placeholder():
    """Mock draft should not contain [Placeholder content for ...]."""
    state = run_pipeline("Quantum Computing")
    assert state.draft.strip() != ""
    assert "[Placeholder content" not in state.draft


def test_pipeline_draft_uses_outline_title():
    state = run_pipeline("The Solar System")
    assert state.outline is not None
    assert state.outline.title in state.draft


def test_pipeline_passes_without_api_keys(monkeypatch):
    """Pipeline must complete fully in mock mode with no API keys set."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "mock")
    state = run_pipeline("Photosynthesis")
    assert state.final_article_package is not None
    errors = validate_final_state(state)
    assert errors == []
