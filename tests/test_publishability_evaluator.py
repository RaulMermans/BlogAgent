"""Tests for the publishability evaluator."""

from __future__ import annotations

from blogagent.agents.publishability_evaluator import (
    PublishabilityEvaluation,
    evaluate_publishability,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_STRONG_ARTICLE = """# The 5 Best Perfumes for a Date Night That Actually Last

If you've ever sat down to dinner and caught a whiff of something unforgettable, you already know
a great scent does half the work. These five fragrances earn their place on your vanity not because
of marketing, but because editors and fragrance experts keep recommending them, and for good reason.

## Quick Picks

- Chanel Chance Eau Tendre — best for a light, romantic first impression
- Yves Saint Laurent Libre — best for confident evening energy
- Dior Miss Dior Blooming Bouquet — best for classic femininity
- Lancôme La Vie Est Belle — best for sweetness and warmth
- Tom Ford Black Orchid — best for bold, unforgettable impact

## How We Chose

We looked at fragrance editor recommendations across [Allure](https://allure.com),
[Fragrantica](https://fragrantica.com), and [Byrdie](https://byrdie.com), focusing on
longevity, sillage, and occasion appropriateness for romantic evenings.

## The Standout Picks

**Chanel Chance Eau Tendre** is our top pick for first dates. Its fresh citrus top notes
and white musk base give it a soft, approachable quality — floral without being heavy.
Best for: casual dinner dates, spring evenings.

**YSL Libre** opens with lavender and orange blossom, settling into a warm vanilla amber base.
The projection is confident without being overpowering. Best for: sophisticated dinner dates.

## Buying Tips

For longevity, apply to pulse points — wrists, neck, inner elbows. Avoid rubbing after applying,
which breaks down the top notes faster. Eau de Parfum concentrations will last 6–8 hours on
most skin types.

## Final Takeaway

For a date night, you want something that lasts through dinner and lingers. Chanel Chance Eau Tendre
is the safe-but-never-boring pick; YSL Libre is for when you want to be remembered.
"""

_GENERIC_ARTICLE = """# A Comprehensive Guide to the Best Perfumes for a Date

In today's world, finding the right perfume can be challenging. Are you looking for the best
options? Look no further! This comprehensive guide will help you find everything you need to know.

## Quick Picks

- Perfume A
- Perfume B
- Perfume C

## How We Chose

We've got you covered with our selection criteria. Without further ado, let's dive in.

## Conclusion

In conclusion, as you can see, choosing a perfume is important. We hope this guide was helpful.
"""

_HIGH_QUALITY_SOURCE = {
    "quality": "high",
    "reason": "allure.com is editorial",
    "url": "https://allure.com",
    "title": "Allure",
}


class TestPublishabilityEvaluator:
    def test_strong_editorial_article_passes(self):
        """A well-written article with sensory detail and POV should pass."""
        result = evaluate_publishability(
            article_markdown=_STRONG_ARTICLE,
            topic="top 5 best perfumes for a date",
            is_recommendation=True,
            selected_skills=["beauty-fragrance-writing", "personal-blog-voice"],
            source_quality_scores=[_HIGH_QUALITY_SOURCE],
            evidence_sufficiency=None,
        )
        assert isinstance(result, PublishabilityEvaluation)
        assert result.score >= 65  # Should score reasonably well
        # Should not have high-severity generic_voice defect
        high_generic = [
            d for d in result.defects
            if d.type == "generic_voice" and d.severity == "high"
        ]
        assert len(high_generic) == 0

    def test_generic_intro_fails_or_polish_required(self):
        """Article with generic intro patterns triggers defect or polish."""
        result = evaluate_publishability(
            article_markdown=_GENERIC_ARTICLE,
            topic="top 5 best perfumes for a date",
            is_recommendation=True,
            selected_skills=["beauty-fragrance-writing"],
            source_quality_scores=[_HIGH_QUALITY_SOURCE],
            evidence_sufficiency=None,
        )
        assert result.polish_required is True or result.score < 80
        # Should find generic voice or weak intro defects
        defect_types = [d.type for d in result.defects]
        assert any(t in defect_types for t in ("generic_voice", "weak_intro"))

    def test_fragrance_article_without_sensory_detail_gets_defect(self):
        """Fragrance article missing scent notes and context gets weak_sensory_detail defect."""
        bare_fragrance = """# Best Perfumes for a Date

## Quick Picks

- Perfume A — a great choice
- Perfume B — another option

## How We Chose

We picked these based on popularity.

## Final Takeaway

These are good options for a date.
"""
        result = evaluate_publishability(
            article_markdown=bare_fragrance,
            topic="best perfumes for a date",
            is_recommendation=True,
            selected_skills=["beauty-fragrance-writing"],
            source_quality_scores=[_HIGH_QUALITY_SOURCE],
            evidence_sufficiency=None,
        )
        sensory_defects = [d for d in result.defects if d.type == "weak_sensory_detail"]
        assert len(sensory_defects) >= 1
        assert sensory_defects[0].severity in ("medium", "high")

    def test_weak_conclusion_gets_defect(self):
        """Article with 'in conclusion...' or 'to summarize' gets weak_conclusion defect."""
        article_with_weak_conclusion = """# Best Laptops

## Quick Picks

- MacBook Pro — best for professionals
- Dell XPS — best for Windows users

## Buying Tips

Consider your budget and workflow.

## Final Takeaway

In conclusion, as you can see, these are the best laptops. We hope this article was helpful.
"""
        result = evaluate_publishability(
            article_markdown=article_with_weak_conclusion,
            topic="best laptops for developers",
            is_recommendation=True,
            selected_skills=["product-recommendation-depth"],
            source_quality_scores=[_HIGH_QUALITY_SOURCE],
            evidence_sufficiency=None,
        )
        conclusion_defects = [d for d in result.defects if d.type == "weak_conclusion"]
        assert len(conclusion_defects) >= 1

    def test_thin_recommendations_fail(self):
        """Recommendation article with picks but no detail gets thin_recommendations defect."""
        thin_rec = """# Top 5 Perfumes for a Date

## Quick Picks

- Chanel No. 5
- Dior Sauvage
- Marc Jacobs Daisy
- Versace Eros
- Gucci Bloom

## How We Chose

Based on research.

## Final Takeaway

All of these are good choices.
"""
        result = evaluate_publishability(
            article_markdown=thin_rec,
            topic="top 5 perfumes for a date",
            is_recommendation=True,
            selected_skills=["product-recommendation-depth"],
            source_quality_scores=[_HIGH_QUALITY_SOURCE],
            evidence_sufficiency=None,
        )
        thin_defects = [d for d in result.defects if d.type == "thin_recommendations"]
        assert len(thin_defects) >= 1

    def test_score_is_0_to_100(self):
        """Score is always in valid range."""
        result = evaluate_publishability(
            article_markdown=_GENERIC_ARTICLE,
            topic="perfumes for a date",
            is_recommendation=True,
            selected_skills=[],
            source_quality_scores=[],
            evidence_sufficiency=None,
        )
        assert 0 <= result.score <= 100

    def test_non_recommendation_non_fragrance_topic(self):
        """Non-recommendation topic doesn't get fragrance-specific defects."""
        article = """# Understanding Photosynthesis

## Introduction

Photosynthesis is how plants convert sunlight into energy. It is fundamental to life on Earth.

## How It Works

Chlorophyll absorbs light. Carbon dioxide and water are converted to glucose and oxygen.

## Conclusion

Worth studying — understanding photosynthesis reveals how ecosystems are powered.
"""
        result = evaluate_publishability(
            article_markdown=article,
            topic="how photosynthesis works",
            is_recommendation=False,
            selected_skills=["citation-grounding"],
            source_quality_scores=[_HIGH_QUALITY_SOURCE],
            evidence_sufficiency=None,
        )
        sensory_defects = [d for d in result.defects if d.type == "weak_sensory_detail"]
        assert len(sensory_defects) == 0
