import pytest
from pydantic import ValidationError

from blogagent.workflow.state import (
    ArticlePackage,
    BlogRunState,
    CitationMatch,
    CitationStatus,
    Claim,
    ClaimImportance,
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
