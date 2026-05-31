"""Tests for the recommendation_extractor module."""

from __future__ import annotations

from blogagent.tools.recommendation_extractor import (
    RecommendationCandidate,
    build_candidates_summary,
    extract_recommendations_from_evidence,
)
from blogagent.workflow.state import EvidenceItem


def _make_evidence(
    fact: str, url: str = "https://example.com", title: str = "Test"
) -> EvidenceItem:
    return EvidenceItem(
        fact=fact,
        source_url=url,
        source_title=title,
        publisher_domain=url.split("/")[2] if "://" in url else "example.com",
        confidence=0.8,
        used_for="background",
    )


def _make_quality(url: str, quality: str) -> dict:
    return {"url": url, "quality": quality, "title": "Test", "reason": "test"}


class TestExtractProductNames:
    def test_extracts_bold_name(self):
        evidence = [_make_evidence("The **Chanel Chance Eau Tendre** is a great summer fragrance.")]
        quality = [_make_quality("https://example.com", "high")]
        candidates = extract_recommendations_from_evidence(evidence, quality)
        names = [c.name for c in candidates]
        assert any("Chanel" in n for n in names), f"Expected Chanel in names, got {names}"

    def test_extracts_numbered_list_item(self):
        snippet = """Here are the top summer perfumes:
1. Dior Sauvage — a fresh, citrus-forward fragrance
2. Gucci Bloom — floral and modern
"""
        evidence = [_make_evidence(snippet)]
        quality = [_make_quality("https://example.com", "high")]
        candidates = extract_recommendations_from_evidence(evidence, quality)
        names = [c.name for c in candidates]
        assert any("Dior" in n for n in names) or any("Gucci" in n for n in names), (
            f"Expected Dior or Gucci in names, got {names}"
        )

    def test_extracts_bullet_list_item(self):
        snippet = "- YSL Libre — best for evening wear\n- Tom Ford Black Orchid — bold and smoky"
        evidence = [_make_evidence(snippet)]
        quality = [_make_quality("https://example.com", "medium")]
        candidates = extract_recommendations_from_evidence(evidence, quality)
        names = [c.name for c in candidates]
        assert any("YSL" in n or "Tom Ford" in n for n in names), (
            f"Expected YSL or Tom Ford in names, got {names}"
        )

    def test_captures_scent_descriptors_near_product(self):
        snippet = (
            "**Chanel Chance Eau Tendre** has fresh citrus notes and white musk base. "
            "Perfect for summer."
        )
        evidence = [_make_evidence(snippet)]
        quality = [_make_quality("https://allure.com", "high")]
        candidates = extract_recommendations_from_evidence(
            evidence, quality, topic="summer perfumes"
        )
        # Should find at least one candidate with sensory terms
        assert len(candidates) > 0
        candidate = candidates[0]
        assert len(candidate.sensory_terms) > 0, (
            f"Expected sensory terms, got {candidate.sensory_terms}"
        )

    def test_captures_suitability_context(self):
        snippet = "1. Dior Sauvage — best for summer, long-lasting, tested by editors"
        evidence = [_make_evidence(snippet)]
        quality = [_make_quality("https://byrdie.com", "high")]
        candidates = extract_recommendations_from_evidence(
            evidence, quality, topic="summer fragrances"
        )
        assert len(candidates) > 0
        candidate = candidates[0]
        assert len(candidate.supported_context) > 0, (
            f"Expected context, got {candidate.supported_context}"
        )

    def test_placeholder_evidence_yields_no_candidates(self):
        evidence = [_make_evidence("Information about best perfumes from Mock Source")]
        quality = [_make_quality("https://example.com", "low")]
        candidates = extract_recommendations_from_evidence(evidence, quality)
        assert candidates == [], f"Expected no candidates from placeholder, got {candidates}"

    def test_empty_evidence_yields_no_candidates(self):
        candidates = extract_recommendations_from_evidence([], [])
        assert candidates == []

    def test_marks_low_quality_single_source_as_low_confidence(self):
        snippet = "1. Chanel No 5 — popular classic"
        evidence = [_make_evidence(snippet, url="https://reddit.com/r/fragrance")]
        quality = [_make_quality("https://reddit.com/r/fragrance", "low")]
        candidates = extract_recommendations_from_evidence(evidence, quality)
        assert len(candidates) > 0
        candidate = candidates[0]
        assert candidate.low_confidence is True, f"Expected low_confidence, got {candidate}"

    def test_low_confidence_candidates_not_usable(self):
        snippet = "1. Dior Sauvage — nice fragrance"
        evidence = [_make_evidence(snippet, url="https://reddit.com/r/fragrance")]
        quality = [_make_quality("https://reddit.com/r/fragrance", "low")]
        candidates = extract_recommendations_from_evidence(evidence, quality)
        usable = [c for c in candidates if c.usable]
        assert len(usable) == 0, (
            f"Expected no usable candidates from low-quality source, got {usable}"
        )

    def test_high_quality_source_candidate_is_usable(self):
        snippet = (
            "**Chanel Chance Eau Tendre** is our top pick for summer. Fresh citrus and musk notes."
        )
        evidence = [_make_evidence(snippet, url="https://allure.com/best-summer-perfumes")]
        quality = [_make_quality("https://allure.com/best-summer-perfumes", "high")]
        candidates = extract_recommendations_from_evidence(evidence, quality)
        usable = [c for c in candidates if c.usable]
        assert len(usable) > 0, (
            f"Expected usable candidates from high-quality source, got {candidates}"
        )

    def test_deduplicates_same_name_across_sources(self):
        snippet1 = "1. Dior Sauvage — fresh citrus fragrance"
        snippet2 = "- Dior Sauvage: our top pick for summer evenings"
        evidence = [
            _make_evidence(snippet1, url="https://allure.com/perfumes"),
            _make_evidence(snippet2, url="https://byrdie.com/fragrances"),
        ]
        quality = [
            _make_quality("https://allure.com/perfumes", "high"),
            _make_quality("https://byrdie.com/fragrances", "high"),
        ]
        candidates = extract_recommendations_from_evidence(evidence, quality)
        dior_candidates = [c for c in candidates if "Dior" in c.name]
        # The canonical "Dior Sauvage" should appear at least once
        assert len(dior_candidates) >= 1, "Expected at least one Dior candidate"
        # The canonical merged candidate should have both source URLs
        canonical = next((c for c in dior_candidates if c.name == "Dior Sauvage"), None)
        if canonical is not None:
            assert len(canonical.source_urls) == 2, (
                f"Expected 2 source URLs for merged candidate, got {canonical.source_urls}"
            )
        # Total distinct Dior-named candidates should not be excessive
        assert len(dior_candidates) <= 4, (
            f"Too many Dior variants: {[c.name for c in dior_candidates]}"
        )


class TestBuildCandidatesSummary:
    def test_summary_counts_usable(self):
        candidates = [
            RecommendationCandidate(
                name="Chanel Chance",
                source_urls=["https://allure.com"],
                source_quality="high",
                supported_context=["summer"],
                sensory_terms=["fresh"],
                usable=True,
                reason="high quality source",
                low_confidence=False,
            ),
            RecommendationCandidate(
                name="Dior Sauvage",
                source_urls=["https://allure.com"],
                source_quality="high",
                supported_context=["summer"],
                sensory_terms=["citrus"],
                usable=True,
                reason="high quality source",
                low_confidence=False,
            ),
            RecommendationCandidate(
                name="Some Reddit Rec",
                source_urls=["https://reddit.com"],
                source_quality="low",
                supported_context=[],
                sensory_terms=[],
                usable=False,
                reason="low quality only",
                low_confidence=True,
            ),
        ]
        summary = build_candidates_summary(candidates)
        assert summary["usable_count"] == 2
        assert summary["low_confidence_count"] == 1
        assert "Chanel Chance" in summary["names"]
        assert "Some Reddit Rec" not in summary["names"]

    def test_empty_candidates_summary(self):
        summary = build_candidates_summary([])
        assert summary["usable_count"] == 0
        assert summary["names"] == []


class TestEvidenceSufficiencyWithCandidates:
    """Integration tests: candidates feed evidence sufficiency correctly."""

    def test_2_usable_of_7_requested_is_insufficient(self):
        from blogagent.agents.evidence_sufficiency import evaluate_evidence_sufficiency

        candidates = [
            {"usable": True, "name": "A"},
            {"usable": True, "name": "B"},
            {"usable": False, "name": "C"},
        ]
        result = evaluate_evidence_sufficiency(
            topic="7 best perfumes",
            requested_count=7,
            is_recommendation=True,
            is_financial=False,
            source_quality_scores=[{"quality": "high", "url": "https://allure.com"}],
            evidence_table=[],
            enrichment_already_ran=False,
            recommendation_candidates=candidates,
        )
        assert result.supported_count == 2
        assert not result.sufficient
        assert result.recommended_action == "search_more"

    def test_7_usable_of_7_requested_is_sufficient(self):
        from blogagent.agents.evidence_sufficiency import evaluate_evidence_sufficiency

        candidates = [{"usable": True, "name": str(i)} for i in range(7)]
        result = evaluate_evidence_sufficiency(
            topic="7 best perfumes",
            requested_count=7,
            is_recommendation=True,
            is_financial=False,
            source_quality_scores=[
                {"quality": "high", "url": f"https://allure.com/{i}"} for i in range(7)
            ],
            evidence_table=[],
            enrichment_already_ran=False,
            recommendation_candidates=candidates,
        )
        assert result.supported_count == 7
        assert result.sufficient

    def test_insufficient_after_enrichment_gives_evidence_limited(self):
        from blogagent.agents.evidence_sufficiency import evaluate_evidence_sufficiency

        candidates = [{"usable": True, "name": str(i)} for i in range(3)]
        result = evaluate_evidence_sufficiency(
            topic="7 best perfumes",
            requested_count=7,
            is_recommendation=True,
            is_financial=False,
            source_quality_scores=[{"quality": "high", "url": "https://allure.com"}],
            evidence_table=[],
            enrichment_already_ran=True,
            recommendation_candidates=candidates,
        )
        assert not result.sufficient
        assert result.recommended_action == "evidence_limited"
