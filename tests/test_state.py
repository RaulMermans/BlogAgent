import pytest
from pydantic import ValidationError

from blogagent.workflow.state import (
    ArticlePackage,
    BlogRunState,
    FactCheckReport,
    SourceScore,
)


def make_fact_check_report(**kwargs) -> FactCheckReport:
    defaults = dict(
        total_claims=0,
        supported_count=0,
        partially_supported_count=0,
        unsupported_count=0,
        passed=True,
    )
    return FactCheckReport(**{**defaults, **kwargs})


def make_source(i: int = 0) -> SourceScore:
    return SourceScore(
        url=f"https://example{i}.com/article",
        title=f"Source {i}",
        domain=f"example{i}.com",
        credibility_score=0.8,
        relevance_score=0.8,
        recency_score=0.8,
        overall_score=0.8,
    )


# ---------------------------------------------------------------------------
# BlogRunState
# ---------------------------------------------------------------------------


def test_blog_run_state_can_be_created():
    state = BlogRunState(topic="Climate Change")
    assert state.topic == "Climate Change"
    assert state.research_questions == []
    assert state.draft == ""
    assert state.final_article_package is None
    assert state.revision_count == 0


def test_blog_run_state_default_lists_are_independent():
    s1 = BlogRunState(topic="A")
    s2 = BlogRunState(topic="B")
    s1.research_questions.append("Q1")
    assert s2.research_questions == [], "Default lists must not be shared across instances"


def test_blog_run_state_has_blocked_fields():
    state = BlogRunState(topic="test")
    assert state.blocked is False
    assert state.block_reason == ""
    assert state.requires_approval is False


def test_blog_run_state_blocked_can_be_set():
    state = BlogRunState(
        topic="test", blocked=True, block_reason="external effect", requires_approval=True
    )
    assert state.blocked is True
    assert state.block_reason == "external effect"
    assert state.requires_approval is True


def test_blog_run_state_has_trace_fields():
    state = BlogRunState(topic="test")
    assert state.warnings == []
    assert state.provider_events == []
    assert state.stage_timings == {}
    assert state.execution_mode == "mock"


def test_blog_run_state_trace_lists_are_independent():
    s1 = BlogRunState(topic="A")
    s2 = BlogRunState(topic="B")
    s1.warnings.append("w1")
    s1.provider_events.append("e1")
    assert s2.warnings == []
    assert s2.provider_events == []


def test_blog_run_state_execution_mode_can_be_set():
    state = BlogRunState(topic="test", execution_mode="live")
    assert state.execution_mode == "live"


def test_pipeline_state_has_provider_events_after_run():
    from blogagent.workflow.graph import run_pipeline

    state = run_pipeline("Photosynthesis")
    assert len(state.provider_events) > 0


def test_pipeline_state_has_stage_timings_after_run():
    from blogagent.workflow.graph import run_pipeline

    state = run_pipeline("Photosynthesis")
    assert len(state.stage_timings) > 0
    assert all(isinstance(v, float) for v in state.stage_timings.values())


def test_pipeline_execution_mode_is_mock_by_default(monkeypatch):
    from blogagent.workflow.graph import run_pipeline

    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "mock")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_EDITOR", "false")
    monkeypatch.setenv("BLOGAGENT_USE_LLM_FACTCHECK", "false")
    monkeypatch.setenv("BLOGAGENT_SEARCH_PROVIDER", "mock")
    state = run_pipeline("Solar Energy")
    assert state.execution_mode == "mock"


def test_pipeline_provider_events_include_search():
    from blogagent.workflow.graph import run_pipeline

    state = run_pipeline("Solar Energy")
    search_events = [e for e in state.provider_events if "search:" in e]
    assert len(search_events) >= 1


# ---------------------------------------------------------------------------
# ArticlePackage
# ---------------------------------------------------------------------------


def test_article_package_valid():
    pkg = ArticlePackage(
        article_markdown="# Title\n\nContent.",
        source_list=[make_source()],
        fact_check_report=make_fact_check_report(),
        claim_support_statuses=[],
        revision_summary="No revisions.",
    )
    assert pkg.article_markdown.startswith("# Title")
    assert pkg.revision_summary == "No revisions."


def test_article_package_has_seo_fields_with_defaults():
    pkg = ArticlePackage(
        article_markdown="# Title\n\nContent.",
        source_list=[make_source()],
        fact_check_report=make_fact_check_report(),
        claim_support_statuses=[],
        revision_summary="No revisions.",
    )
    assert pkg.title == ""
    assert pkg.slug == ""
    assert pkg.meta_description == ""
    assert pkg.seo_keywords == []


def test_article_package_seo_fields_can_be_set():
    pkg = ArticlePackage(
        article_markdown="# Title\n\nContent.",
        source_list=[make_source()],
        fact_check_report=make_fact_check_report(),
        claim_support_statuses=[],
        revision_summary="No revisions.",
        title="Understanding Climate Change",
        slug="understanding-climate-change",
        meta_description="A comprehensive guide to climate change.",
        seo_keywords=["climate change", "global warming"],
    )
    assert pkg.title == "Understanding Climate Change"
    assert pkg.slug == "understanding-climate-change"
    assert pkg.meta_description == "A comprehensive guide to climate change."
    assert pkg.seo_keywords == ["climate change", "global warming"]


def test_article_package_requires_article_markdown():
    with pytest.raises((ValidationError, TypeError)):
        ArticlePackage(
            source_list=[],
            fact_check_report=make_fact_check_report(),
            claim_support_statuses=[],
            revision_summary="",
        )


def test_article_package_requires_fact_check_report():
    with pytest.raises((ValidationError, TypeError)):
        ArticlePackage(
            article_markdown="# Title",
            source_list=[],
            fact_check_report=None,  # type: ignore[arg-type]
            claim_support_statuses=[],
            revision_summary="done",
        )


def test_article_package_requires_revision_summary():
    with pytest.raises((ValidationError, TypeError)):
        ArticlePackage(
            article_markdown="# Title",
            source_list=[],
            fact_check_report=make_fact_check_report(),
            claim_support_statuses=[],
        )
