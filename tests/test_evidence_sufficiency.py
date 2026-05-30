"""Tests for the evidence sufficiency evaluator."""

from __future__ import annotations

from blogagent.agents.evidence_sufficiency import (
    EvidenceSufficiencyResult,
    evaluate_evidence_sufficiency,
    generate_enrichment_queries,
)
from blogagent.workflow.state import EvidenceItem


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_source_quality(quality: str, is_mock: bool = False) -> dict:
    reason = "Mock placeholder source" if is_mock else f"{quality} source"
    return {
        "url": f"https://example.com/{quality}",
        "title": f"{quality} source",
        "quality": quality,
        "reason": reason,
    }


def _make_evidence_item(
    fact: str = "Great perfume with floral notes",
    source_url: str = "https://allure.com/1",
) -> EvidenceItem:
    return EvidenceItem(
        fact=fact,
        source_url=source_url,
        source_title="Allure",
        publisher_domain="allure.com",
        confidence=0.8,
        used_for="recommendation",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEvidenceSufficiencyRecommendation:
    def test_top10_with_5_supported_returns_insufficient(self):
        """top 10 with only 5 supported recommendation sources → insufficient."""
        source_quality = [_make_source_quality("high")] * 2 + [_make_source_quality("medium")] * 1
        evidence = [
            _make_evidence_item(f"Pick #{i}", f"https://example.com/{i}")
            for i in range(3)
        ]
        result = evaluate_evidence_sufficiency(
            topic="top 10 best perfumes for a date",
            requested_count=10,
            is_recommendation=True,
            is_financial=False,
            source_quality_scores=source_quality,
            evidence_table=evidence,
            enrichment_already_ran=False,
        )
        assert isinstance(result, EvidenceSufficiencyResult)
        assert result.sufficient is False
        assert result.requested_count == 10
        assert result.supported_count < 10
        assert "search_more" == result.recommended_action
        assert len(result.missing) >= 1

    def test_sufficient_recommendation_evidence_passes(self):
        """5 high/medium sources with 10 evidence items → sufficient for top 5."""
        source_quality = [_make_source_quality("high")] * 4 + [_make_source_quality("medium")] * 4
        evidence = [
            _make_evidence_item(
                f"Named pick #{i} floral notes fresh citrus",
                f"https://allure.com/{i}",
            )
            for i in range(10)
        ]
        result = evaluate_evidence_sufficiency(
            topic="top 5 best perfumes for a date",
            requested_count=5,
            is_recommendation=True,
            is_financial=False,
            source_quality_scores=source_quality,
            evidence_table=evidence,
            enrichment_already_ran=False,
        )
        assert result.sufficient is True
        assert result.recommended_action == "proceed"

    def test_low_source_dominance_lowers_score(self):
        """All low-quality sources lower the score compared to high-quality baseline."""
        source_quality_low = [_make_source_quality("low")] * 5
        source_quality_high = [_make_source_quality("high")] * 5
        evidence = [_make_evidence_item() for _ in range(5)]
        result_low = evaluate_evidence_sufficiency(
            topic="best perfumes for a date",
            requested_count=None,
            is_recommendation=True,
            is_financial=False,
            source_quality_scores=source_quality_low,
            evidence_table=evidence,
            enrichment_already_ran=False,
        )
        result_high = evaluate_evidence_sufficiency(
            topic="best perfumes for a date",
            requested_count=None,
            is_recommendation=True,
            is_financial=False,
            source_quality_scores=source_quality_high,
            evidence_table=evidence,
            enrichment_already_ran=False,
        )
        # Low-quality sources should produce a lower score
        assert result_low.score < result_high.score
        # Warning about low quality should appear
        assert any("low-quality" in m or "editorial authority" in m for m in result_low.missing)

    def test_evidence_limited_after_max_search_pass(self):
        """After enrichment ran, recommendation still uses 'evidence_limited' not 'search_more'."""
        source_quality = [_make_source_quality("high")] * 2
        evidence = [_make_evidence_item() for _ in range(2)]
        result = evaluate_evidence_sufficiency(
            topic="top 10 best perfumes for a date",
            requested_count=10,
            is_recommendation=True,
            is_financial=False,
            source_quality_scores=source_quality,
            evidence_table=evidence,
            enrichment_already_ran=True,
        )
        assert result.sufficient is False
        assert result.recommended_action == "evidence_limited"

    def test_no_requested_count_proceeds(self):
        """No requested count with decent evidence → proceed."""
        source_quality = [_make_source_quality("high")] * 3
        evidence = [
            _make_evidence_item(f"Good pick #{i}", f"https://allure.com/{i}")
            for i in range(5)
        ]
        result = evaluate_evidence_sufficiency(
            topic="best perfumes for a date",
            requested_count=None,
            is_recommendation=True,
            is_financial=False,
            source_quality_scores=source_quality,
            evidence_table=evidence,
            enrichment_already_ran=False,
        )
        assert result.recommended_action in ("proceed", "evidence_limited")

    def test_non_recommendation_topic_proceeds(self):
        """Non-recommendation topics pass through with 'proceed'."""
        source_quality = [_make_source_quality("medium")] * 3
        evidence = [_make_evidence_item("Factual info about photosynthesis") for _ in range(3)]
        result = evaluate_evidence_sufficiency(
            topic="how photosynthesis works",
            requested_count=None,
            is_recommendation=False,
            is_financial=False,
            source_quality_scores=source_quality,
            evidence_table=evidence,
            enrichment_already_ran=False,
        )
        assert result.recommended_action == "proceed"

    def test_mock_sources_treated_as_insufficient(self):
        """Mock placeholder sources count as insufficient for recommendation."""
        source_quality = [_make_source_quality("low", is_mock=True)] * 5
        evidence = [
            EvidenceItem(
                fact=f"Information about top perfumes from source {i}",
                source_url=f"https://mock-{i}.example.dev/",
                source_title=f"[MOCK] Source {i}",
                publisher_domain=f"mock-{i}.example.dev",
                confidence=0.3,
                used_for="background",
            )
            for i in range(5)
        ]
        result = evaluate_evidence_sufficiency(
            topic="top 5 perfumes for a date",
            requested_count=5,
            is_recommendation=True,
            is_financial=False,
            source_quality_scores=source_quality,
            evidence_table=evidence,
            enrichment_already_ran=False,
        )
        assert result.sufficient is False


class TestGenerateEnrichmentQueries:
    def test_generates_queries_for_fragrance(self):
        queries = generate_enrichment_queries(
            topic="top 10 best perfumes for a date",
            missing=["Evidence supports ~5 recommendations; 5 more needed"],
            requested_count=10,
        )
        assert len(queries) == 3
        assert all(isinstance(q, str) and len(q) > 5 for q in queries)

    def test_removes_top_n_prefix(self):
        queries = generate_enrichment_queries(
            topic="top 10 best perfumes for a date",
            missing=[],
            requested_count=10,
        )
        # Queries should not start with "top 10 best"
        for q in queries:
            assert "top 10 best" not in q.lower()
