"""Tests for count_recommendations — the deterministic recommendation counter.

Requirements covered:
- Bullet Quick Picks (- / *) counted correctly
- Numbered Quick Picks (1. / 1)) counted correctly
- Heading-based recommendations counted correctly
- Source URLs / source list entries do NOT inflate count
- Evidence-limited exception detection
"""

from __future__ import annotations

from blogagent.agents.quality_evaluator import _is_evidence_limited_article, count_recommendations

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_BULLET_QP_5 = """# The 5 Best Perfumes for a Date Night

## Quick Picks

- Chanel No. 5 — A timeless floral
- Lancôme La Vie Est Belle — Sweet and romantic
- Yves Saint Laurent Libre — Bold and feminine
- Dior Miss Dior — Elegant and fresh
- Guerlain Mon Guerlain — Soft lavender

## How We Chose

We evaluated longevity, sillage, and romantic character.

## Final Takeaway

These five fragrances stood out across expert sources.
"""

_NUMBERED_QP_10 = """# Top 10 Fragrances for a Date

## Quick Picks

1. Chanel Chance Eau Tendre
2. Tom Ford Black Orchid
3. Lancôme La Vie Est Belle
4. Yves Saint Laurent Mon Paris
5. Dior Miss Dior Blooming Bouquet
6. Viktor & Rolf Flowerbomb
7. Guerlain Mon Guerlain
8. Jo Malone Peony & Blush Suede
9. Maison Margiela Replica Flower Market
10. Dolce & Gabbana Light Blue

## How We Chose

Longevity, versatility, and date-night appeal.
"""

_STAR_BULLETS_3 = """# Best Telescopes for Beginners

## Quick Picks

* Celestron NexStar 5SE
* Orion StarBlast 4.5
* Sky-Watcher Evostar 80

## How We Chose

We evaluated telescopes based on aperture, mount quality, and ease of use.
"""

_HEADING_NUMBERED_5 = """# 5 Evidence-Backed Perfumes for a Date Night

## 1. Chanel No. 5

A classic floral.

## 2. Lancôme La Vie Est Belle

Sweet and romantic.

## 3. Yves Saint Laurent Libre

Bold and feminine.

## 4. Dior Miss Dior

Elegant and fresh.

## 5. Guerlain Mon Guerlain

Soft lavender.

## Final Takeaway

These five represent the best-supported options.
"""

_WITH_SOURCES = """# Top 5 Perfumes

## Quick Picks

- Chanel No. 5
- Lancôme La Vie Est Belle
- Yves Saint Laurent Libre
- Dior Miss Dior
- Guerlain Mon Guerlain

## Sources

- https://fragrantica.com/best-date-perfumes
- https://byrdie.com/top-date-fragrances
- https://allure.com/best-perfumes-for-dates
"""

_EMPTY_QP = """# Best Perfumes

## Quick Picks

No specific recommendations available — enable real search.

## How We Chose

We looked at editorial sources.
"""

_NO_QP = """# Introduction to Perfumes

## What Makes a Good Date Fragrance

Choose a scent that is not overpowering.

## Conclusion

Pick what you love.
"""

_EVIDENCE_LIMITED = """# 5 Evidence-Backed Perfumes for a Date Night

## Quick Picks

- Chanel No. 5
- Lancôme La Vie Est Belle
- Yves Saint Laurent Libre
- Dior Miss Dior
- Guerlain Mon Guerlain

## Introduction

The available evidence supported only 5 distinct perfume recommendations from our sources.
We requested 10 but evidence did not support the full count.

## Final Takeaway

These five are the best-supported options from available evidence.
"""

_NO_EVIDENCE_LIMITED = """# Best Perfumes for a Date

## Quick Picks

- Chanel No. 5
- Lancôme La Vie Est Belle
- Yves Saint Laurent Libre
- Dior Miss Dior
- Guerlain Mon Guerlain

## Introduction

Here are the top picks.
"""


# ---------------------------------------------------------------------------
# count_recommendations tests
# ---------------------------------------------------------------------------


def test_bullet_quick_picks_5():
    assert count_recommendations(_BULLET_QP_5) == 5


def test_numbered_quick_picks_10():
    assert count_recommendations(_NUMBERED_QP_10) == 10


def test_star_bullets_3():
    assert count_recommendations(_STAR_BULLETS_3) == 3


def test_heading_numbered_5():
    assert count_recommendations(_HEADING_NUMBERED_5) == 5


def test_sources_section_not_counted():
    """Source URL bullet list must not inflate the recommendation count."""
    count = count_recommendations(_WITH_SOURCES)
    assert count == 5, f"Expected 5 recommendations, got {count}"


def test_empty_quick_picks_returns_0():
    """Quick Picks section with no list items → count 0."""
    assert count_recommendations(_EMPTY_QP) == 0


def test_no_quick_picks_no_numbered_headings_returns_0():
    assert count_recommendations(_NO_QP) == 0


def test_no_sources_section_does_not_affect_count():
    draft = "# Top 3\n\n## Quick Picks\n\n- A\n- B\n- C\n"
    assert count_recommendations(draft) == 3


def test_mixed_bullets_and_numbered_in_quick_picks():
    """Both bullets and numbered items in Quick Picks should both be counted."""
    draft = "# Top 4\n\n## Quick Picks\n\n- A\n1. B\n- C\n2. D\n"
    assert count_recommendations(draft) == 4


def test_quick_picks_preferred_over_numbered_headings():
    """If Quick Picks section has items, use that count, not heading count."""
    draft = _NUMBERED_QP_10 + "\n## 1. Extra Heading\n\nSome text.\n"
    assert count_recommendations(draft) == 10


def test_case_insensitive_quick_picks():
    draft = "# Top 2\n\n## QUICK PICKS\n\n- A\n- B\n"
    assert count_recommendations(draft) == 2


# ---------------------------------------------------------------------------
# _is_evidence_limited_article tests
# ---------------------------------------------------------------------------


def test_evidence_limited_accepted_when_explained():
    assert (
        _is_evidence_limited_article(_EVIDENCE_LIMITED, actual_count=5, requested_count=10) is True
    )


def test_evidence_limited_rejected_when_no_explanation():
    assert (
        _is_evidence_limited_article(_NO_EVIDENCE_LIMITED, actual_count=5, requested_count=10)
        is False
    )


def test_evidence_limited_rejected_when_title_claims_wrong_count():
    draft = (
        "# Top 10 Perfumes for a Date\n\n## Quick Picks\n\n"
        "- A\n- B\n\nThe available evidence supported only 2.\n"
    )
    assert _is_evidence_limited_article(draft, actual_count=2, requested_count=10) is False


def test_evidence_limited_accepted_with_corrected_title():
    draft = (
        "# 5 Evidence-Backed Perfumes\n\n## Quick Picks\n\n"
        "- A\n- B\n- C\n- D\n- E\n\nEvidence supported only 5 recommendations.\n"
    )
    assert _is_evidence_limited_article(draft, actual_count=5, requested_count=10) is True
