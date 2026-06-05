"""Tests for the deterministic source quality classifier."""

from __future__ import annotations

import pytest

from blogagent.tools.source_quality import SourceQuality, classify_source_quality
from blogagent.workflow.state import SourceScore


def _make_score(domain: str, title: str = "Test", is_mock: bool = False) -> SourceScore:
    return SourceScore(
        url=f"https://{domain}/article",
        title=title,
        domain=domain,
        credibility_score=0.7,
        relevance_score=0.7,
        recency_score=0.7,
        overall_score=0.7,
        is_mock=is_mock,
    )


def test_mock_source_is_low():
    result = classify_source_quality(_make_score("example.dev", is_mock=True))
    assert result.quality == "low"
    assert "mock" in result.reason.lower()


@pytest.mark.parametrize(
    "domain",
    [
        "quora.com",
        "reddit.com",
        "instagram.com",
        "tiktok.com",
        "pinterest.com",
        "twitter.com",
        "x.com",
    ],
)
def test_social_domains_are_low(domain: str):
    result = classify_source_quality(_make_score(domain))
    assert result.quality == "low", f"Expected low for {domain}, got {result.quality}"


@pytest.mark.parametrize(
    "domain",
    [
        "wikipedia.org",
        "britannica.com",
        "bbc.com",
        "reuters.com",
        "nytimes.com",
        "wirecutter.com",
        "tomsguide.com",
        "techradar.com",
        "theverge.com",
        "cnet.com",
        "rtings.com",
        "trustedreviews.com",
        "whathifi.com",
        "gearpatrol.com",
        "hodinkee.com",
        "teddy-baldassarre.com",
        "bobswatches.com",
        "watchtime.com",
        "ablogtowatch.com",
        "consumerreports.org",
        "pcmag.com",
        "allure.com",
        "realsimple.com",
        "marieclaire.com",
        "editorialist.com",
    ],
)
def test_editorial_domains_are_high(domain: str):
    result = classify_source_quality(_make_score(domain))
    assert result.quality == "high", f"Expected high for {domain}, got {result.quality}"


def test_fragrantica_domain_is_medium():
    """fragrantica.com should be medium (community/database), not high."""
    result = classify_source_quality(_make_score("fragrantica.com"))
    assert result.quality == "medium", f"Expected medium for fragrantica.com, got {result.quality}"


def test_fragrantica_forum_url_is_low():
    """fragrantica.com/forum/ paths should be classified as low (user-generated)."""
    from blogagent.workflow.state import SourceScore

    score = SourceScore(
        url="https://www.fragrantica.com/forum/t/12345",
        title="Forum post",
        domain="fragrantica.com",
        credibility_score=0.5,
        relevance_score=0.5,
        recency_score=0.5,
        overall_score=0.5,
        is_mock=False,
    )
    result = classify_source_quality(score)
    assert result.quality == "low", (
        f"Expected low for fragrantica.com/forum/ URL, got {result.quality}"
    )


def test_bluemercury_is_medium():
    result = classify_source_quality(_make_score("bluemercury.com"))
    assert result.quality == "medium"


def test_thebeautylookbook_is_medium():
    result = classify_source_quality(_make_score("thebeautylookbook.com"))
    assert result.quality == "medium"


def test_edu_domain_is_high():
    result = classify_source_quality(_make_score("stanford.edu"))
    assert result.quality == "high"


def test_gov_domain_is_high():
    result = classify_source_quality(_make_score("irs.gov"))
    assert result.quality == "high"


def test_unknown_domain_is_medium():
    result = classify_source_quality(_make_score("some-random-blog.net"))
    assert result.quality == "medium"


def test_returns_source_quality_model():
    result = classify_source_quality(_make_score("bbc.com"))
    assert isinstance(result, SourceQuality)
    assert result.url
    assert result.title
    assert result.quality in ("high", "medium", "low")
    assert result.reason
