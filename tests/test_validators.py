from blogagent.tools.validators import (
    validate_article_package,
    validate_minimum_sources,
    validate_no_unsupported_high_importance_claims,
)
from blogagent.workflow.state import (
    ArticlePackage,
    CitationMatch,
    CitationStatus,
    Claim,
    ClaimImportance,
    FactCheckReport,
    SourceScore,
)


def _fact_check() -> FactCheckReport:
    return FactCheckReport(
        total_claims=0,
        supported_count=0,
        partially_supported_count=0,
        unsupported_count=0,
        passed=True,
    )


def _source(i: int = 0) -> SourceScore:
    return SourceScore(
        url=f"https://example{i}.com/article",
        title=f"Source {i}",
        domain=f"example{i}.com",
        credibility_score=0.8,
        relevance_score=0.8,
        recency_score=0.8,
        overall_score=0.8,
    )


def _pkg(**kwargs) -> ArticlePackage:
    defaults = dict(
        article_markdown="# Title\n\nContent.",
        source_list=[_source(i) for i in range(3)],
        fact_check_report=_fact_check(),
        claim_support_statuses=[],
        revision_summary="No revisions.",
        title="Test Title",
        slug="test-title",
    )
    return ArticlePackage(**{**defaults, **kwargs})


# --- validate_article_package ---


def test_validate_article_package_valid():
    assert validate_article_package(_pkg()) == []


def test_validate_article_package_empty_markdown():
    errors = validate_article_package(_pkg(article_markdown=""))
    assert any("article_markdown" in e for e in errors)


def test_validate_article_package_empty_revision_summary():
    errors = validate_article_package(_pkg(revision_summary=""))
    assert any("revision_summary" in e for e in errors)


def test_validate_article_package_empty_source_list():
    errors = validate_article_package(_pkg(source_list=[]))
    assert any("source_list" in e for e in errors)


def test_validate_article_package_empty_title():
    errors = validate_article_package(_pkg(title=""))
    assert any("title" in e for e in errors)


def test_validate_article_package_empty_slug():
    errors = validate_article_package(_pkg(slug=""))
    assert any("slug" in e for e in errors)


# --- validate_minimum_sources ---


def test_validate_minimum_sources_passes_with_three():
    assert validate_minimum_sources(_pkg()) == []


def test_validate_minimum_sources_fails_with_two():
    errors = validate_minimum_sources(_pkg(source_list=[_source(0), _source(1)]))
    assert len(errors) == 1
    assert "minimum" in errors[0]


def test_validate_minimum_sources_custom_minimum():
    assert validate_minimum_sources(_pkg(source_list=[_source()]), minimum=1) == []


# --- validate_no_unsupported_high_importance_claims ---


def test_no_unsupported_high_importance_passes_when_supported():
    claim = Claim(text="X is true.", importance=ClaimImportance.high)
    match = CitationMatch(
        claim=claim,
        status=CitationStatus.supported,
        supporting_sources=["https://example.com"],
    )
    errors = validate_no_unsupported_high_importance_claims(_pkg(claim_support_statuses=[match]))
    assert errors == []


def test_no_unsupported_high_importance_fails_when_unsupported():
    claim = Claim(text="X is true.", importance=ClaimImportance.high)
    match = CitationMatch(claim=claim, status=CitationStatus.unsupported)
    errors = validate_no_unsupported_high_importance_claims(_pkg(claim_support_statuses=[match]))
    assert len(errors) == 1
    assert "X is true." in errors[0]


def test_no_unsupported_high_importance_passes_for_medium_unsupported():
    claim = Claim(text="Y is probably true.", importance=ClaimImportance.medium)
    match = CitationMatch(claim=claim, status=CitationStatus.unsupported)
    errors = validate_no_unsupported_high_importance_claims(_pkg(claim_support_statuses=[match]))
    assert errors == [], "Medium unsupported claims must not block finalization"
