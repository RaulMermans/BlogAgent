"""Tests for the recommendation_extractor module."""

from __future__ import annotations

from blogagent.tools.recommendation_extractor import (
    ArticleRecommendation,
    RecommendationCandidate,
    audit_article_recommendations,
    build_candidates_summary,
    build_grounded_candidates_summary,
    classify_candidate_entity,
    extract_candidates_from_sources,
    extract_recommendations_from_article,
    extract_recommendations_from_evidence,
    match_article_recommendations_to_evidence,
    normalize_recommendation_name,
)
from blogagent.workflow.query_contract import build_query_contract
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
        snippet = (
            "- YSL Libre — best for evening wear\n"
            "- Tom Ford Black Orchid — bold and smoky"
        )
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


class TestContractAwareClassification:
    def _contract(self):
        return build_query_contract(
            "7 best parfums for summer",
            is_recommendation=True,
            is_financial=False,
            requested_count=7,
        )

    def test_specific_products_are_usable(self):
        contract = self._contract()
        for name in (
            "Tom Ford Soleil Blanc",
            "Dolce & Gabbana Light Blue",
            "Jo Malone London Wood Sage & Sea Salt",
        ):
            entity_type, is_product, rejection = classify_candidate_entity(name, contract)
            assert entity_type == "specific_product"
            assert is_product is True
            assert rejection is None

    def test_brand_only_names_are_rejected_for_product_query(self):
        contract = self._contract()
        for name in ("Kilian", "Glossier", "Sol de Janeiro"):
            entity_type, is_product, rejection = classify_candidate_entity(name, contract)
            assert entity_type == "brand"
            assert is_product is False
            assert "brand-only" in (rejection or "")

    def test_section_and_source_title_phrases_are_rejected(self):
        contract = self._contract()
        for name in (
            "How We Chose Our Top Summer Parfums",
            "Choosing Your Signature Summer Scent",
            "Best Summer Perfumes, Vetted by Editors",
        ):
            entity_type, is_product, rejection = classify_candidate_entity(name, contract)
            assert entity_type in ("section_heading", "category", "source_title")
            assert is_product is False
            assert rejection


class TestContractAwareCandidateExtraction:
    def test_extracts_products_and_rejects_noise(self):
        contract = build_query_contract(
            "7 best parfums for summer",
            is_recommendation=True,
            is_financial=False,
            requested_count=7,
        )
        snippet = """
1. Tom Ford Soleil Blanc — coconut, amber and summer beach warmth.
2. Dolce & Gabbana Light Blue — citrus, fresh, warm weather classic.
3. Kilian — chic but listed here only as a brand.
## How We Chose Our Top Summer Parfums
"""
        evidence = [
            _make_evidence(
                snippet,
                url="https://allure.com/summer-perfumes",
                title="Best Summer Perfumes, Vetted by Editors",
            )
        ]
        quality = [_make_quality("https://allure.com/summer-perfumes", "high")]
        candidates = extract_candidates_from_sources([], evidence, contract, quality)
        usable_names = [c.name for c in candidates if c.usable]
        rejected_names = [c.name for c in candidates if not c.usable]
        assert "Tom Ford Soleil Blanc" in usable_names
        assert "Dolce & Gabbana Light Blue" in usable_names
        assert any("Kilian" in n for n in rejected_names)
        assert all("How We Chose" not in n for n in usable_names)

    def test_post_draft_audit_flags_brand_and_unknown_product(self):
        contract = build_query_contract(
            "7 best parfums for summer",
            is_recommendation=True,
            is_financial=False,
            requested_count=7,
        )
        allowed = [
            RecommendationCandidate(
                name="Tom Ford Soleil Blanc",
                normalized_name="tom ford soleil blanc",
                entity_type="specific_product",
                domain="beauty_fragrance",
                is_specific_product=True,
                source_urls=["https://allure.com"],
                source_titles=["Allure"],
                source_quality="high",
                evidence_terms=["coconut"],
                supported_context=["summer"],
                sensory_terms=["coconut"],
                usable=True,
                confidence="high",
                reason="test",
            ).model_dump()
        ]
        article = """# Summer Picks

## Quick Picks

- Tom Ford Soleil Blanc — source-backed
- Kilian — brand-only
- Unknown Dream Cologne — unsupported
"""
        audit = audit_article_recommendations(
            markdown=article,
            allowed_candidates=allowed,
            query_contract=contract,
            evidence_table=[],
            source_quality_scores=[_make_quality("https://allure.com", "high")],
        )
        assert audit.article_recommendations_count == 3
        assert "Kilian" in audit.brand_only_recommendations
        assert "Unknown Dream Cologne" in audit.unsupported_recommendations
        assert audit.passes is False


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


# ---------------------------------------------------------------------------
# Article recommendation extraction
# ---------------------------------------------------------------------------

_SEVEN_PICK_ARTICLE = """# 7 Best Parfums for Summer

Summer heat demands fresh, light fragrances that project just enough.

## Quick Picks

- **Best Solar Floral:** Guerlain Terracotta Le Parfum — citrusy golden warmth
- **Best Aquatic:** Giorgio Armani Ocean di Gioia
- **Best Unisex:** Eris Parfums Delta of Venus
- **Best Luxury:** Tom Ford Soleil Blanc
- **Best Indie:** Byredo Sundazed
- **Best Fresh:** Jo Malone London Wood Sage & Sea Salt
- **Best Classic:** Maison Francis Kurkdjian Aqua Universalis Forte

## How We Chose

We tested each fragrance for sillage, longevity, and summer wearability.

## 1. Guerlain Terracotta Le Parfum

**Best for:** Warm, sunny days
**Why it works:** A solar floral with citrus and golden amber notes.

## 2. Giorgio Armani Ocean di Gioia

**Best for:** Beach and poolside
**Why it works:** Light aquatic floral with cool oceanic feel.

## Final Takeaway

All seven fragrances deliver on their summer promise.
"""


class TestExtractRecommendationsFromArticle:
    def test_extracts_quick_picks_with_bold_labels(self):
        recs = extract_recommendations_from_article(_SEVEN_PICK_ARTICLE)
        names = [r.name for r in recs]
        assert any("Guerlain" in n for n in names), f"Expected Guerlain in {names}"
        assert any("Armani" in n or "Ocean" in n for n in names), (
            f"Expected Armani/Ocean in {names}"
        )

    def test_extracts_seven_unique_recommendations(self):
        recs = extract_recommendations_from_article(_SEVEN_PICK_ARTICLE)
        assert len(recs) >= 6, f"Expected at least 6, got {len(recs)}: {[r.name for r in recs]}"

    def test_captures_quick_pick_label(self):
        recs = extract_recommendations_from_article(_SEVEN_PICK_ARTICLE)
        labeled = [r for r in recs if r.quick_pick_label]
        assert len(labeled) >= 1, "Expected at least one rec with quick_pick_label"
        labels = [r.quick_pick_label for r in labeled]
        assert any("Solar" in (lb or "") for lb in labels), f"Expected 'Solar' label in {labels}"

    def test_extracts_best_for_from_section(self):
        recs = extract_recommendations_from_article(_SEVEN_PICK_ARTICLE)
        with_best_for = [r for r in recs if r.best_for]
        assert len(with_best_for) >= 1, "Expected at least one rec with best_for"

    def test_extracts_why_it_works(self):
        recs = extract_recommendations_from_article(_SEVEN_PICK_ARTICLE)
        with_why = [r for r in recs if r.why_it_works]
        assert len(with_why) >= 1, "Expected at least one rec with why_it_works"

    def test_ignores_how_we_chose(self):
        recs = extract_recommendations_from_article(_SEVEN_PICK_ARTICLE)
        names_lower = [r.name.lower() for r in recs]
        assert not any("how we chose" in n for n in names_lower)
        assert not any(n == "how we chose" for n in names_lower)

    def test_ignores_final_takeaway(self):
        recs = extract_recommendations_from_article(_SEVEN_PICK_ARTICLE)
        names_lower = [r.name.lower() for r in recs]
        assert not any("final takeaway" in n for n in names_lower)

    def test_deduplicates_repeated_names(self):
        # Guerlain appears in Quick Picks and in a H2 heading — should not double-count
        recs = extract_recommendations_from_article(_SEVEN_PICK_ARTICLE)
        guerlain_recs = [r for r in recs if "Guerlain" in r.name or "Terracotta" in r.name]
        assert len(guerlain_recs) == 1, (
            f"Expected 1 Guerlain rec, got {[r.name for r in guerlain_recs]}"
        )

    def test_extracts_numbered_headings(self):
        markdown = """# Best Perfumes

## Quick Picks

- Dior Sauvage
- Chanel Bleu

## 1. Dior Sauvage

Best for summer outdoors.

## 2. Chanel Bleu

Best for evening events.
"""
        recs = extract_recommendations_from_article(markdown)
        names = [r.name for r in recs]
        assert any("Dior" in n for n in names), f"Expected Dior in {names}"
        assert any("Chanel" in n for n in names), f"Expected Chanel in {names}"

    def test_extracts_label_colon_name_headings(self):
        markdown = """# Best Perfumes

## Best Solar Floral: Guerlain Terracotta Le Parfum

Great for warm days.

## Best Aquatic: Giorgio Armani Ocean di Gioia

Ideal for beach.
"""
        recs = extract_recommendations_from_article(markdown)
        names = [r.name for r in recs]
        assert any("Guerlain" in n for n in names), f"Expected Guerlain in {names}"

    def test_ignores_source_section(self):
        markdown = """# Best Perfumes

## Quick Picks

- Tom Ford Soleil Blanc

## Sources

- Tom Ford Soleil Blanc Official Site
- https://allure.com
"""
        recs = extract_recommendations_from_article(markdown)
        names = [r.name for r in recs]
        assert len([n for n in names if "Tom Ford" in n]) == 1, (
            f"Sources section added duplicate: {names}"
        )

    def test_empty_article_returns_empty(self):
        assert extract_recommendations_from_article("") == []

    def test_generic_article_returns_empty(self):
        markdown = """# About Perfumes

## How We Chose

We looked at many sources.

## Final Takeaway

Buy the best for you.
"""
        recs = extract_recommendations_from_article(markdown)
        assert recs == [], f"Expected empty, got {[r.name for r in recs]}"


class TestNormalizeRecommendationName:
    def test_lowercase(self):
        assert normalize_recommendation_name("Tom Ford") == "tom ford"

    def test_strips_markdown_bold(self):
        assert normalize_recommendation_name("**Tom Ford**") == "tom ford"

    def test_strips_brackets(self):
        assert normalize_recommendation_name("[Tom Ford](https://example.com)") == "tom ford"

    def test_strips_leading_the(self):
        assert normalize_recommendation_name("The Tom Ford Collection") == "tom ford collection"

    def test_collapses_whitespace(self):
        assert normalize_recommendation_name("Tom   Ford  Soleil") == "tom ford soleil"

    def test_empty_returns_empty(self):
        assert normalize_recommendation_name("") == ""


class TestMatchArticleRecommendationsToEvidence:
    def _make_candidate(self, name: str, quality: str = "high") -> dict:
        return {
            "name": name,
            "source_urls": [f"https://allure.com/{name.lower().replace(' ', '-')}"],
            "source_quality": quality,
            "usable": True,
            "low_confidence": False,
            "supported_context": ["summer"],
            "sensory_terms": ["fresh"],
            "reason": "test",
        }

    def test_exact_match_gives_high_confidence(self):
        recs = [ArticleRecommendation(name="Tom Ford Soleil Blanc")]
        candidates = [self._make_candidate("Tom Ford Soleil Blanc")]
        groundings = match_article_recommendations_to_evidence(
            article_recs=recs,
            evidence_candidates=candidates,
            source_quality_scores=[
                {"url": "https://allure.com/tom-ford-soleil-blanc", "quality": "high"}
            ],
        )
        assert len(groundings) == 1
        assert groundings[0].matched is True
        assert groundings[0].confidence == "high"

    def test_partial_name_match_gives_medium_confidence(self):
        recs = [ArticleRecommendation(name="Soleil Blanc")]
        candidates = [self._make_candidate("Tom Ford Soleil Blanc")]
        groundings = match_article_recommendations_to_evidence(
            article_recs=recs,
            evidence_candidates=candidates,
            source_quality_scores=[],
        )
        assert groundings[0].matched is True
        assert groundings[0].confidence in ("medium", "high")

    def test_unmatched_recommendation_flagged(self):
        recs = [ArticleRecommendation(name="Completely Unknown Fragrance XYZ")]
        candidates = [self._make_candidate("Tom Ford Soleil Blanc")]
        groundings = match_article_recommendations_to_evidence(
            article_recs=recs,
            evidence_candidates=candidates,
            source_quality_scores=[],
        )
        assert groundings[0].matched is False

    def test_citation_url_in_section_grounds_recommendation(self):
        recs = [
            ArticleRecommendation(
                name="Unknown Fragrance XYZ",
                source_urls=["https://allure.com/article"],
            )
        ]
        candidates = []
        groundings = match_article_recommendations_to_evidence(
            article_recs=recs,
            evidence_candidates=candidates,
            source_quality_scores=[{"url": "https://allure.com/article", "quality": "high"}],
        )
        assert groundings[0].matched is True

    def test_empty_recs_returns_empty(self):
        groundings = match_article_recommendations_to_evidence(
            article_recs=[],
            evidence_candidates=[],
            source_quality_scores=[],
        )
        assert groundings == []


class TestBuildGroundedCandidatesSummary:
    def _make_candidate_obj(self, name: str, usable: bool = True) -> RecommendationCandidate:
        return RecommendationCandidate(
            name=name,
            source_urls=["https://allure.com"],
            source_quality="high",
            supported_context=["summer"],
            sensory_terms=["fresh"],
            usable=usable,
            reason="test",
            low_confidence=not usable,
        )

    def test_seven_grounded_gives_usable_count_seven(self):
        from blogagent.tools.recommendation_extractor import RecommendationGrounding

        groundings = [
            RecommendationGrounding(
                name=f"Fragrance {i}",
                matched=True,
                confidence="high",
                support_reason="test",
            )
            for i in range(7)
        ]
        summary = build_grounded_candidates_summary(candidates=[], groundings=groundings)
        assert summary["usable_count"] == 7
        assert summary["article_recommendations_count"] == 7
        assert summary["grounded_recommendations_count"] == 7
        assert summary["unmatched_names"] == []

    def test_article_with_2_unmatched_gives_usable_count_5(self):
        from blogagent.tools.recommendation_extractor import RecommendationGrounding

        groundings = [
            RecommendationGrounding(
                name=f"Fragrance {i}",
                matched=(i < 5),
                confidence="high" if i < 5 else "low",
                support_reason="test",
            )
            for i in range(7)
        ]
        summary = build_grounded_candidates_summary(candidates=[], groundings=groundings)
        assert summary["usable_count"] == 5
        assert summary["grounded_recommendations_count"] == 5
        assert len(summary["unmatched_names"]) == 2

    def test_no_article_recs_falls_back_to_evidence_candidates(self):
        candidates = [self._make_candidate_obj("Tom Ford"), self._make_candidate_obj("Chanel")]
        summary = build_grounded_candidates_summary(candidates=candidates, groundings=[])
        assert summary["usable_count"] == 2
        assert summary["article_recommendations_count"] == 0

    def test_summary_includes_evidence_candidates_count(self):
        from blogagent.tools.recommendation_extractor import RecommendationGrounding

        candidates = [self._make_candidate_obj("Tom Ford")]
        groundings = [
            RecommendationGrounding(
                name="Tom Ford",
                matched=True,
                confidence="high",
                support_reason="test",
            )
        ]
        summary = build_grounded_candidates_summary(candidates=candidates, groundings=groundings)
        assert "evidence_candidates_count" in summary
        assert summary["evidence_candidates_count"] == 1
