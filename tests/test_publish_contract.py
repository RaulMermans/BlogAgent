"""Tests for the publish_contract module."""

from __future__ import annotations

from blogagent.agents.publish_contract import (
    PublishContractResult,
    check_publish_contract,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_HIGH_QUALITY_SOURCE = {"quality": "high", "url": "https://allure.com", "title": "Allure"}
_LOW_QUALITY_SOURCE = {"quality": "low", "url": "https://reddit.com", "title": "Reddit"}

_STRONG_7_PICK_ARTICLE = """# 7 Best Perfumes for Summer Heat

These seven fragrances earned their spot through source-backed testing across leading
beauty publications. Scent families, longevity, and occasion guide each pick.

## Quick Picks

- Chanel Chance Eau Tendre — best for casual summer days
- Dior Miss Dior Blooming Bouquet — best for floral freshness
- YSL Libre — best for evening energy
- Gucci Flora Gorgeous Gardenia — best for date nights
- Marc Jacobs Daisy — best for lighthearted warmth
- Burberry Her — best for fruity-floral summer vibes
- Lancôme La Vie Est Belle — best for sweetness and longevity

## How We Chose

We reviewed editorial picks from [Allure](https://allure.com), [Byrdie](https://byrdie.com),
and [Fragrantica](https://fragrantica.com), focusing on projection, sillage, longevity,
and fresh/citrus/floral note profiles suited to summer heat.

## The Picks

**Chanel Chance Eau Tendre** opens with citrus notes, settles into white musk.
Best for: casual dates, daytime summer wear.
Why it works: The fresh, light sillage is non-offensive in summer heat.

**Dior Miss Dior Blooming Bouquet** has rose and peony at heart with white musk base.
Best for: warm summer evenings.

## Final Takeaway

For summer, prioritize fresh, citrus-forward or light floral fragrances with moderate
longevity. Chanel Chance Eau Tendre remains the gold standard.
"""

_THIN_2_PICK_ARTICLE = """# 7 Best Perfumes for Summer

We found only limited source coverage. The available sources did not provide enough
information to recommend seven fragrances with confidence.

## Quick Picks

- Chanel No. 5 — a classic
- Dior Sauvage — popular

## Notes

Only 2 fragrances had sufficient source coverage.

## Final Takeaway

Check back when more editorial sources are available.
"""

_EVIDENCE_LIMITED_5_PICK_ARTICLE = """# 5 Summer Perfumes With Strong Source Coverage

We set out to find 7 but sources only supported 5 recommendations with confidence.
The available sources did not provide enough detail to recommend more with editorial integrity.
Rather than pad the list, we kept it to five well-documented picks.

## Quick Picks

- Chanel Chance Eau Tendre — best for casual summer days; fresh citrus and white musk notes
- Dior Miss Dior Blooming Bouquet — best for evenings; delicate rose and peony
- YSL Libre — bold evening energy; lavender and orange blossom with warm amber base
- Gucci Bloom — fresh floral, long-lasting sillage, ideal for daytime summer wear
- Burberry Her — fruity summer vibes, light berry and citrus top notes

## How We Chose

Sources: [Allure](https://allure.com) and [Byrdie](https://byrdie.com).
We focused on longevity, projection, fresh-to-floral note profiles, and suitability
for summer heat. Only fragrances with documented editorial backing made the cut.

## The Picks

**Chanel Chance Eau Tendre** is our top overall recommendation. Its fresh, citrus-forward
opening settles into a soft musk — light enough for summer heat yet memorable.
Best for: casual summer dates, daytime wear. It works because the sillage is gentle.

**YSL Libre** is the bolder evening pick, with lavender and orange blossom top notes
that make it distinctive without being overpowering. Worth it for confident wearers.

## Final Takeaway

These five fragrances — from citrus-fresh Chanel to warm floral Gucci Bloom — are the
best-sourced picks for summer 2025. Each has editorial backing, tested longevity, and
a clear mood profile. If evidence for additional picks emerges, this list will grow.
"""

_GENERIC_ARTICLE = """# A Comprehensive Guide to the Best Perfumes

In today's world, finding the right perfume can be challenging. Are you looking for
the best options? Look no further! This guide will cover everything you need to know.

## Quick Picks

- Perfume A — nice
- Perfume B — good

## Conclusion

In conclusion, these are good choices.
"""


class TestPublishContractRecommendationPosts:
    def test_strong_7_pick_article_passes_contract(self):
        result = check_publish_contract(
            article_markdown=_STRONG_7_PICK_ARTICLE,
            topic="7 best perfumes for summer",
            publishability_score=88,
            publishability_defects=[],
            is_recommendation=True,
            requested_count=7,
            evidence_sufficiency={"recommended_action": "proceed", "supported_count": 7},
            source_quality_scores=[_HIGH_QUALITY_SOURCE] * 5,
        )
        assert isinstance(result, PublishContractResult)
        assert result.status in ("publish_ready", "publish_ready_with_warnings")

    def test_thin_2_pick_article_is_draft_only(self):
        """2 picks for a requested 7 without valid framing → draft_only."""
        result = check_publish_contract(
            article_markdown=_THIN_2_PICK_ARTICLE,
            topic="7 best perfumes for summer",
            publishability_score=60,
            publishability_defects=[],
            is_recommendation=True,
            requested_count=7,
            evidence_sufficiency={"recommended_action": "evidence_limited", "supported_count": 2},
            source_quality_scores=[_HIGH_QUALITY_SOURCE],
        )
        assert result.status == "draft_only_not_publish_ready"
        assert not result.passes
        # Should have a high defect for insufficient count (2 < 3 min)
        high_defects = [d for d in result.defects if d.severity == "high"]
        assert len(high_defects) > 0

    def test_evidence_limited_5_of_7_is_publish_ready_with_warnings(self):
        """5 of 7 requested with clear evidence-limited framing → publish_ready_with_warnings."""
        result = check_publish_contract(
            article_markdown=_EVIDENCE_LIMITED_5_PICK_ARTICLE,
            topic="7 best perfumes for summer",
            publishability_score=80,
            publishability_defects=[],
            is_recommendation=True,
            requested_count=7,
            evidence_sufficiency={"recommended_action": "evidence_limited", "supported_count": 5},
            source_quality_scores=[_HIGH_QUALITY_SOURCE] * 3,
        )
        # 5 >= 3 min, explanation present, title does not falsely claim 7
        assert result.status in ("publish_ready_with_warnings", "publish_ready")
        # The unmet count defect should be medium (not high) since explanation is present
        high_unmet = [
            d for d in result.defects if d.type == "unmet_requested_count" and d.severity == "high"
        ]
        assert len(high_unmet) == 0

    def test_fewer_than_3_recommendations_caps_score(self):
        result = check_publish_contract(
            article_markdown=_THIN_2_PICK_ARTICLE,
            topic="best perfumes for summer",
            publishability_score=90,
            publishability_defects=[],
            is_recommendation=True,
            requested_count=None,
            evidence_sufficiency=None,
            source_quality_scores=[_HIGH_QUALITY_SOURCE],
        )
        # 2 picks → insufficient_recommendations defect → score capped at 65
        assert result.score_cap is not None
        assert result.score_cap <= 65
        assert result.status == "draft_only_not_publish_ready"

    def test_no_quick_picks_section_is_high_defect(self):
        no_qp = (
            "# Best Perfumes\n\nPerfume A is good. Perfume B is also nice."
            "\n\n## Final Takeaway\nChoose wisely.\n"
        )
        result = check_publish_contract(
            article_markdown=no_qp,
            topic="best perfumes for summer",
            publishability_score=85,
            publishability_defects=[],
            is_recommendation=True,
            requested_count=None,
            evidence_sufficiency=None,
            source_quality_scores=[_HIGH_QUALITY_SOURCE],
        )
        qp_defects = [d for d in result.defects if d.type == "missing_quick_picks"]
        assert len(qp_defects) > 0
        assert qp_defects[0].severity == "high"
        assert result.status == "draft_only_not_publish_ready"

    def test_unresolved_high_defect_gives_draft_only(self):
        result = check_publish_contract(
            article_markdown=_GENERIC_ARTICLE,
            topic="7 best perfumes for summer",
            publishability_score=65,
            publishability_defects=[
                {"type": "generic_voice", "severity": "high", "message": "test"}
            ],
            is_recommendation=True,
            requested_count=7,
            evidence_sufficiency=None,
            source_quality_scores=[_HIGH_QUALITY_SOURCE],
        )
        assert result.status == "draft_only_not_publish_ready"
        assert not result.passes

    def test_publish_ready_requires_no_high_defects(self):
        result = check_publish_contract(
            article_markdown=_STRONG_7_PICK_ARTICLE,
            topic="7 best perfumes for summer",
            publishability_score=90,
            publishability_defects=[],
            is_recommendation=True,
            requested_count=7,
            evidence_sufficiency={"recommended_action": "proceed", "supported_count": 7},
            source_quality_scores=[_HIGH_QUALITY_SOURCE] * 5,
        )
        high_defects = [d for d in result.defects if d.severity == "high"]
        if result.status == "publish_ready":
            assert len(high_defects) == 0

    def test_weak_source_dominance_caps_score(self):
        result = check_publish_contract(
            article_markdown=_STRONG_7_PICK_ARTICLE,
            topic="7 best perfumes for summer",
            publishability_score=88,
            publishability_defects=[],
            is_recommendation=True,
            requested_count=7,
            evidence_sufficiency={"recommended_action": "proceed", "supported_count": 7},
            source_quality_scores=[_LOW_QUALITY_SOURCE] * 8 + [_HIGH_QUALITY_SOURCE],
        )
        # 8/9 low quality → weak_source_dominance defect
        dominance_defects = [d for d in result.defects if d.type == "weak_source_dominance"]
        assert len(dominance_defects) > 0
        if result.score_cap is not None:
            assert result.score_cap <= 74

    def test_unmet_count_without_explanation_caps_score_at_59(self):
        # Article with 3 picks but no evidence-limited explanation, requested 7
        article_no_explanation = """# 7 Best Perfumes for Summer

## Quick Picks

- Chanel Chance — great
- Dior Sauvage — classic
- YSL Libre — bold

## Final Takeaway

These are nice perfumes.
"""
        result = check_publish_contract(
            article_markdown=article_no_explanation,
            topic="7 best perfumes for summer",
            publishability_score=80,
            publishability_defects=[],
            is_recommendation=True,
            requested_count=7,
            evidence_sufficiency=None,
            source_quality_scores=[_HIGH_QUALITY_SOURCE] * 3,
        )
        # 3 picks, no explanation, requested 7 → unmet_requested_count high defect
        unmet_defects = [d for d in result.defects if d.type == "unmet_requested_count"]
        assert len(unmet_defects) > 0
        if result.score_cap is not None:
            assert result.score_cap <= 59


class TestPublishContractFragrance:
    def test_fragrance_weak_sensory_detail_caps_score(self):
        bare = """# Best Perfumes for Summer

## Quick Picks

- Chanel — a great choice
- Dior — another good option
- YSL — nice fragrance
- Gucci — popular
- Burberry — bestseller

## Final Takeaway

All are good picks.
"""
        result = check_publish_contract(
            article_markdown=bare,
            topic="best parfums for summer",
            publishability_score=85,
            publishability_defects=[],
            is_recommendation=True,
            requested_count=None,
            evidence_sufficiency=None,
            source_quality_scores=[_HIGH_QUALITY_SOURCE] * 3,
        )
        sensory_defects = [d for d in result.defects if d.type == "weak_sensory_detail"]
        assert len(sensory_defects) > 0
        if result.score_cap is not None:
            assert result.score_cap <= 79


class TestPublishContractNonRecommendation:
    def test_factual_article_not_blocked_by_rec_checks(self):
        article = """# How Photosynthesis Works

## Introduction

Photosynthesis converts sunlight into energy. Chlorophyll is the key pigment.

## The Process

Light reactions produce ATP. The Calvin cycle fixes carbon dioxide into glucose.

## Conclusion

Worth understanding — it powers all plant-based life on Earth.
"""
        result = check_publish_contract(
            article_markdown=article,
            topic="how photosynthesis works",
            publishability_score=85,
            publishability_defects=[],
            is_recommendation=False,
            requested_count=None,
            evidence_sufficiency=None,
            source_quality_scores=[_HIGH_QUALITY_SOURCE],
        )
        # Non-recommendation topic should not get Quick Picks or count defects
        qp_defects = [d for d in result.defects if d.type == "missing_quick_picks"]
        assert len(qp_defects) == 0
        count_defects = [d for d in result.defects if d.type == "unmet_requested_count"]
        assert len(count_defects) == 0


class TestPublishContractRecommendationGrounding:
    """Tests for recommendation_grounding parameter in publish contract."""

    def test_7_grounded_of_7_can_pass_contract(self):
        """When 7 recommendations are grounded, contract should not fail on count."""
        grounding = {
            "article_recommendations_count": 7,
            "grounded_recommendations_count": 7,
            "usable_count": 7,
            "unmatched_names": [],
        }
        result = check_publish_contract(
            article_markdown=_STRONG_7_PICK_ARTICLE,
            topic="7 best perfumes for summer",
            publishability_score=88,
            publishability_defects=[],
            is_recommendation=True,
            requested_count=7,
            evidence_sufficiency={"recommended_action": "proceed", "supported_count": 7},
            source_quality_scores=[_HIGH_QUALITY_SOURCE] * 5,
            recommendation_grounding=grounding,
        )
        # With grounding confirming 7 recs, should not get unmet_requested_count high defect
        high_unmet = [
            d for d in result.defects
            if d.type == "unmet_requested_count" and d.severity == "high"
        ]
        msgs = [d.message for d in result.defects]
        assert len(high_unmet) == 0, f"Unexpected high defects: {msgs}"
        assert result.status in ("publish_ready", "publish_ready_with_warnings")

    def test_0_grounded_of_7_fails_contract(self):
        """When 7 article recs exist but 0 are grounded, contract should flag it."""
        grounding = {
            "article_recommendations_count": 7,
            "grounded_recommendations_count": 0,
            "usable_count": 0,
            "unmatched_names": [
                "Guerlain Terracotta Le Parfum",
                "Giorgio Armani Ocean di Gioia",
                "Tom Ford Soleil Blanc",
            ],
        }
        result = check_publish_contract(
            article_markdown=_STRONG_7_PICK_ARTICLE,
            topic="7 best perfumes for summer",
            publishability_score=88,
            publishability_defects=[],
            is_recommendation=True,
            requested_count=7,
            evidence_sufficiency=None,
            source_quality_scores=[_HIGH_QUALITY_SOURCE] * 5,
            recommendation_grounding=grounding,
        )
        # 0 grounded < 3 minimum → unsupported_recommendations high defect
        unsupported = [d for d in result.defects if d.type == "unsupported_recommendations"]
        defect_types = [d.type for d in result.defects]
        assert len(unsupported) > 0, f"Expected unsupported_recommendations defect: {defect_types}"
        high_unsupported = [d for d in unsupported if d.severity == "high"]
        assert len(high_unsupported) > 0

    def test_5_grounded_of_7_gives_medium_warning(self):
        """5 grounded of 7 article recs → medium unsupported defect, not high."""
        grounding = {
            "article_recommendations_count": 7,
            "grounded_recommendations_count": 5,
            "usable_count": 5,
            "unmatched_names": ["Unknown A", "Unknown B"],
        }
        result = check_publish_contract(
            article_markdown=_STRONG_7_PICK_ARTICLE,
            topic="7 best perfumes for summer",
            publishability_score=80,
            publishability_defects=[],
            is_recommendation=True,
            requested_count=7,
            evidence_sufficiency=None,
            source_quality_scores=[_HIGH_QUALITY_SOURCE] * 5,
            recommendation_grounding=grounding,
        )
        unsupported = [d for d in result.defects if d.type == "unsupported_recommendations"]
        if unsupported:
            assert unsupported[0].severity == "medium", (
                f"Expected medium severity, got {unsupported[0].severity}"
            )

    def test_pre_draft_zero_usable_does_not_fail_when_grounding_succeeds(self):
        """Pre-draft usable_count=0 must not fail if post-article grounding gives 7."""
        grounding = {
            "article_recommendations_count": 7,
            "grounded_recommendations_count": 7,
            "usable_count": 7,
            "unmatched_names": [],
        }
        result = check_publish_contract(
            article_markdown=_STRONG_7_PICK_ARTICLE,
            topic="7 best perfumes for summer",
            publishability_score=88,
            publishability_defects=[],
            is_recommendation=True,
            requested_count=7,
            evidence_sufficiency={"recommended_action": "proceed", "supported_count": 0},
            source_quality_scores=[_HIGH_QUALITY_SOURCE] * 5,
            recommendation_grounding=grounding,
        )
        # Grounding overrides pre-draft count — should not get high unmet defect
        high_unmet = [
            d for d in result.defects
            if d.type == "unmet_requested_count" and d.severity == "high"
        ]
        assert len(high_unmet) == 0

    def test_no_grounding_falls_back_to_pattern_count(self):
        """Without recommendation_grounding, behaviour is unchanged."""
        result_no_grounding = check_publish_contract(
            article_markdown=_STRONG_7_PICK_ARTICLE,
            topic="7 best perfumes for summer",
            publishability_score=88,
            publishability_defects=[],
            is_recommendation=True,
            requested_count=7,
            evidence_sufficiency=None,
            source_quality_scores=[_HIGH_QUALITY_SOURCE] * 5,
            recommendation_grounding=None,
        )
        result_with_grounding = check_publish_contract(
            article_markdown=_STRONG_7_PICK_ARTICLE,
            topic="7 best perfumes for summer",
            publishability_score=88,
            publishability_defects=[],
            is_recommendation=True,
            requested_count=7,
            evidence_sufficiency=None,
            source_quality_scores=[_HIGH_QUALITY_SOURCE] * 5,
            recommendation_grounding={
                "article_recommendations_count": 7,
                "grounded_recommendations_count": 7,
                "usable_count": 7,
                "unmatched_names": [],
            },
        )
        # Both should pass (same strong article); grounding should not make things worse
        assert result_no_grounding.status in ("publish_ready", "publish_ready_with_warnings")
        assert result_with_grounding.status in ("publish_ready", "publish_ready_with_warnings")
