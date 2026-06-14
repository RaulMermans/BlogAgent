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
            d for d in result.defects if d.type == "generic_voice" and d.severity == "high"
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


class TestPublishabilityEvaluatorStrict:
    """Tests for the recalibrated, stricter publishability evaluator."""

    _FRAGRANCE_ARTICLE_NO_SENSORY = """# Best Summer Perfumes

## Quick Picks

- Chanel Chance — a great choice for summer
- Dior Sauvage — popular and long-lasting
- YSL Libre — nice option for evenings

## How We Chose

Based on editorial recommendations from beauty publications.

## Final Takeaway

These are all solid choices for the summer season. Each one works well
in warm weather and has earned positive editorial coverage.
"""

    _FRAGRANCE_ARTICLE_RICH_SENSORY = """# 5 Best Summer Perfumes That Actually Last

Fresh, citrus, and aquatic notes define a good summer fragrance. Longevity matters
when you're sweating through the afternoon. These five have the projection and sillage
to survive heat — and the editorial backing to prove it.

## Quick Picks

- Chanel Chance Eau Tendre — fresh citrus, white musk; best for casual dates
- Dior Sauvage — bergamot and woody amber; best for confident wearers
- YSL Libre — lavender and orange blossom with a warm vanilla base
- Gucci Bloom — floral heart, powdery dry down, long longevity
- Burberry Her — fruity-floral, light citrus opening, great for summer days

## The Picks

**Chanel Chance Eau Tendre** opens with fresh citrus and settles into white musk.
Best for: summer dates, daytime. Sillage: gentle. Worth it for everyday wear.

**Dior Sauvage** has bergamot at the top, settling into a woody, amber base.
Best for: evening wear. Projection: moderate. Don't wear in a closed space.

## Final Takeaway

For summer, choose fresh, citrus-forward or light floral fragrances.
The standout: Chanel Chance Eau Tendre — never wrong.
"""

    def test_fragrance_weak_sensory_triggers_polish(self):
        """Fragrance article with < 3 sensory terms must trigger polish_required."""
        result = evaluate_publishability(
            article_markdown=self._FRAGRANCE_ARTICLE_NO_SENSORY,
            topic="best summer perfumes",
            is_recommendation=True,
            selected_skills=["beauty-fragrance-writing"],
            source_quality_scores=[_HIGH_QUALITY_SOURCE],
            evidence_sufficiency=None,
        )
        sensory_defects = [d for d in result.defects if d.type == "weak_sensory_detail"]
        assert len(sensory_defects) >= 1
        assert result.polish_required is True

    def test_fragrance_strong_sensory_no_high_sensory_defect(self):
        """Fragrance article with rich sensory detail should not get a HIGH sensory defect."""
        result = evaluate_publishability(
            article_markdown=self._FRAGRANCE_ARTICLE_RICH_SENSORY,
            topic="5 best perfumes for summer",
            is_recommendation=True,
            selected_skills=["beauty-fragrance-writing"],
            source_quality_scores=[_HIGH_QUALITY_SOURCE] * 3,
            evidence_sufficiency=None,
        )
        high_sensory_defects = [
            d for d in result.defects if d.type == "weak_sensory_detail" and d.severity == "high"
        ]
        assert len(high_sensory_defects) == 0, (
            "Should not have HIGH sensory defect with rich sensory content; "
            f"defects: {result.defects}"
        )

    def test_unmet_count_adds_defect(self):
        """Article with fewer picks than requested triggers unmet_requested_count defect."""
        # Only 3 picks, but 7 requested, with no explanation
        article_3_of_7 = """# 7 Best Summer Perfumes

## Quick Picks

- Chanel Chance — best for summer
- Dior Sauvage — great for evenings
- YSL Libre — bold and lasting

## Final Takeaway

These are good choices for the summer.
"""
        result = evaluate_publishability(
            article_markdown=article_3_of_7,
            topic="7 best summer perfumes",
            is_recommendation=True,
            selected_skills=[],
            source_quality_scores=[_HIGH_QUALITY_SOURCE],
            evidence_sufficiency=None,
            requested_count=7,
        )
        unmet_defects = [d for d in result.defects if d.type == "unmet_requested_count"]
        assert len(unmet_defects) >= 1
        assert unmet_defects[0].severity == "high"

    def test_evidence_limited_framing_lowers_unmet_count_severity(self):
        """Article that explains evidence limitation gets medium (not high) unmet defect."""
        article_5_of_7_explained = """# 5 Best Summer Perfumes With Editorial Backing

We aimed for 7 but the available sources did not provide enough coverage for more.
These 5 have strong editorial support and documented scent profiles.

## Quick Picks

- Chanel Chance Eau Tendre — fresh citrus and musk; best for casual summer
- Dior Miss Dior — rose and peony; best for evenings
- YSL Libre — lavender-warm; bold evening energy
- Gucci Bloom — floral, long-lasting sillage
- Burberry Her — fruity summer vibes, citrus opening

## How We Chose

Reviewed [Allure](https://allure.com) and [Byrdie](https://byrdie.com).

## Final Takeaway

These five offer the best editorial support available. Check for updates as more
fragrance reviews are published. Fresh and floral notes dominate — worth it.
"""
        result = evaluate_publishability(
            article_markdown=article_5_of_7_explained,
            topic="7 best summer perfumes",
            is_recommendation=True,
            selected_skills=[],
            source_quality_scores=[_HIGH_QUALITY_SOURCE] * 3,
            evidence_sufficiency=None,
            requested_count=7,
        )
        high_unmet = [
            d for d in result.defects if d.type == "unmet_requested_count" and d.severity == "high"
        ]
        # With valid evidence-limited framing, the defect should not be HIGH
        assert len(high_unmet) == 0, (
            "Should not have HIGH unmet_requested_count with valid explanation; "
            f"defects: {result.defects}"
        )

    def test_core_medium_defect_triggers_polish(self):
        """Any medium defect in a core domain (weak_pov, weak_sensory_detail) triggers polish."""
        # Article with ~4 sensory terms (medium sensory defect)
        article_medium_sensory = """# Best Summer Perfumes

If you want to smell great this summer, these fragrances are worth considering.
Fresh citrus and floral notes are your best bet for the season.

## Quick Picks

- Chanel Chance — fresh opening, floral heart, long-lasting
- Dior Sauvage — citrus and woody notes, popular choice
- YSL Libre — warm and bold, good for evenings

## How We Chose

We reviewed editorial picks from [Allure](https://allure.com).

## Final Takeaway

Worth it for the summer — these are reliable, editorial-backed picks.
"""
        result = evaluate_publishability(
            article_markdown=article_medium_sensory,
            topic="best summer perfumes",
            is_recommendation=True,
            selected_skills=["beauty-fragrance-writing"],
            source_quality_scores=[_HIGH_QUALITY_SOURCE],
            evidence_sufficiency=None,
        )
        # If there's a medium weak_sensory_detail defect, polish_required must be True
        medium_sensory = [
            d for d in result.defects if d.type == "weak_sensory_detail" and d.severity == "medium"
        ]
        if medium_sensory:
            assert result.polish_required is True, (
                "Medium weak_sensory_detail should trigger polish_required"
            )

    def test_generic_intro_triggers_polish(self):
        """Generic intro (2+ generic phrases) triggers polish_required=True."""
        generic_intro_article = """# Best Perfumes for Summer

In today's world, finding the right perfume can be challenging. Are you looking for the
perfect summer scent? Look no further! This article will cover everything you need.

## Quick Picks

- Chanel Chance — great citrus fragrance
- Dior Sauvage — woody, fresh notes
- YSL Libre — floral and warm

## Final Takeaway

Worth the investment for the summer season.
"""
        result = evaluate_publishability(
            article_markdown=generic_intro_article,
            topic="best perfumes for summer",
            is_recommendation=True,
            selected_skills=[],
            source_quality_scores=[_HIGH_QUALITY_SOURCE],
            evidence_sufficiency=None,
        )
        assert result.polish_required is True

    def test_publish_ready_threshold_is_75(self):
        """Advisory publish_ready should require score >= 75 with no high defects."""
        # Strong article should score well
        result = evaluate_publishability(
            article_markdown=_STRONG_ARTICLE,
            topic="top 5 best perfumes for a date",
            is_recommendation=True,
            selected_skills=["beauty-fragrance-writing"],
            source_quality_scores=[_HIGH_QUALITY_SOURCE],
            evidence_sufficiency=None,
        )
        high_defects = [d for d in result.defects if d.severity == "high"]
        if result.publish_ready:
            assert result.score >= 75
            assert len(high_defects) == 0


# ---------------------------------------------------------------------------
# Requirement 9: a perfect (100) score must be impossible with structural defects
# ---------------------------------------------------------------------------

_MALFORMED_HEADING_ARTICLE = """# Best Tools for Writers

## Quick Picks

- Tool One — best for drafting
- Tool Two — best for editing

## https://example.com/tool-one

**Best for:** writers who want a clean drafting space

A genuinely useful tool with a thoughtful editor and distraction-free mode for focused work.

## $499

**Best for:** teams who need collaboration features

A solid collaborative option with shared workspaces and version history built in for teams.

## Final Takeaway

Either tool will serve most writers well depending on whether you work solo or on a team.
"""

_REPEATED_PARAGRAPH_ARTICLE = """# Best Espresso Machines for Home Baristas

Choosing the right espresso machine can transform your morning routine into a small
daily ritual that you genuinely look forward to each day before anything else happens.

## Quick Picks

- Breville Barista Express — best for built-in grinding
- Gaggia Classic Pro — best for no-frills simplicity

## Breville Barista Express

Choosing the right espresso machine can transform your morning routine into a small
daily ritual that you genuinely look forward to each day before anything else happens.

**Best for:** home baristas who want grinding and brewing in one machine.

## Gaggia Classic Pro

A reliable workhorse that has earned cult status among home enthusiasts for its
simplicity, upgrade potential, and the satisfying ritual of manual operation.

## Final Takeaway

Both machines reward the extra effort with genuinely better espresso at home.
"""

_LEAKED_PIPELINE_NOTES_ARTICLE = """# Best Running Shoes for Daily Training

## Quick Picks

- Shoe One — best for cushioned long runs
- Shoe Two — best for speed days

## Shoe One

- **Source**: Not explicitly mentioned
- A dependable trainer that holds up across varied terrain and weekly mileage.

## Shoe Two

- **Source**: Not explicitly mentioned
- A lighter option built for tempo runs and race-day efforts when pace matters most.

## Final Takeaway

Either shoe rewards consistent training with reliable comfort and durability over time.
"""

_BROKEN_QUOTE_ARTICLE = """# Best Running Shoes for Daily Training

These shoes are built for runners who want consistent comfort and durability across long miles.

## Quick Picks

- Shoe One — best for cushioned long runs
- Shoe Two — best for speed days

## The Standout Picks

One tester said, "This shoe felt like running on clouds from the very first mile and kept that
comfort through marathon training.

## Final Takeaway

Either shoe rewards consistent training with reliable comfort and durability over time.
"""


class TestPublishabilityStructuralFloor:
    """A perfect score must be impossible when the article has structural defects —
    no amount of strong voice, sensory detail, or POV should mask malformed headings,
    repeated paragraphs, or leaked internal pipeline notes."""

    def test_malformed_headings_prevent_perfect_score(self):
        result = evaluate_publishability(
            article_markdown=_MALFORMED_HEADING_ARTICLE,
            topic="best tools for writers",
            is_recommendation=True,
            selected_skills=[],
            source_quality_scores=[_HIGH_QUALITY_SOURCE],
            evidence_sufficiency=None,
        )
        structural_defects = [d for d in result.defects if d.type == "structural_defect"]
        assert structural_defects
        assert structural_defects[0].severity == "high"
        assert result.score < 100
        assert result.score <= 75
        assert result.publish_ready is False
        assert result.polish_required is True

    def test_repeated_paragraphs_prevent_perfect_score(self):
        result = evaluate_publishability(
            article_markdown=_REPEATED_PARAGRAPH_ARTICLE,
            topic="best espresso machines for home baristas",
            is_recommendation=True,
            selected_skills=[],
            source_quality_scores=[_HIGH_QUALITY_SOURCE],
            evidence_sufficiency=None,
        )
        structural_defects = [d for d in result.defects if d.type == "structural_defect"]
        assert structural_defects
        assert "repeat" in structural_defects[0].message.lower()
        assert result.score < 100

    def test_leaked_pipeline_notes_prevent_perfect_score(self):
        result = evaluate_publishability(
            article_markdown=_LEAKED_PIPELINE_NOTES_ARTICLE,
            topic="best running shoes for daily training",
            is_recommendation=True,
            selected_skills=[],
            source_quality_scores=[_HIGH_QUALITY_SOURCE],
            evidence_sufficiency=None,
        )
        structural_defects = [d for d in result.defects if d.type == "structural_defect"]
        assert structural_defects
        assert "not explicitly mentioned" in structural_defects[0].message.lower()
        assert result.score < 100
        assert result.publish_ready is False

    def test_clean_article_has_no_structural_defect(self):
        """A clean article should not be penalized by the structural floor check."""
        result = evaluate_publishability(
            article_markdown=_STRONG_ARTICLE,
            topic="top 5 best perfumes for a date",
            is_recommendation=True,
            selected_skills=["beauty-fragrance-writing"],
            source_quality_scores=[_HIGH_QUALITY_SOURCE],
            evidence_sufficiency=None,
        )
        assert not any(d.type == "structural_defect" for d in result.defects)

    def test_structural_defect_forces_high_severity_and_polish(self):
        """structural_defect must be high severity so it forces polish + blocks publish_ready."""
        result = evaluate_publishability(
            article_markdown=_MALFORMED_HEADING_ARTICLE,
            topic="best tools for writers",
            is_recommendation=True,
            selected_skills=[],
            source_quality_scores=[_HIGH_QUALITY_SOURCE],
            evidence_sufficiency=None,
        )
        assert result.polish_required is True
        assert result.publish_ready is False

    def test_broken_quote_guard(self):
        """A paragraph with an unclosed quotation mark (truncated source quote)
        must be flagged as a structural defect."""
        result = evaluate_publishability(
            article_markdown=_BROKEN_QUOTE_ARTICLE,
            topic="best running shoes for daily training",
            is_recommendation=True,
            selected_skills=[],
            source_quality_scores=[_HIGH_QUALITY_SOURCE],
            evidence_sufficiency=None,
        )
        structural_defects = [d for d in result.defects if d.type == "structural_defect"]
        assert structural_defects
        assert structural_defects[0].severity == "high"
        assert "quotation mark" in structural_defects[0].message.lower()
