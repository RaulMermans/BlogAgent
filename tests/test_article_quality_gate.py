"""Tests for the deterministic Article Quality Gate.

These tests check that the gate:
- Catches internal pipeline language leaking into published articles
- Catches structural defects (malformed headings, repeated paragraphs, generic intros)
- Catches recommendation-specific issues (missing/duplicate "Best for", count mismatch)
- Scores clean, human-readable articles highly and assigns publish_ready ceiling
"""

from __future__ import annotations

from blogagent.tools.article_quality_gate import (
    ArticleQualityGateResult,
    run_article_quality_gate,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_CLEAN_RECOMMENDATION_ARTICLE = """# 5 Best Automatic Watches Under $2000: Our Picks

Walk into any watch forum and you'll find the same five names mentioned again and
again. We put them side by side to see which ones actually earn their reputation.

## Quick Picks

- Tissot PRX Quartz
- Seiko 5 Sports
- Hamilton Khaki Field Mechanical
- Orient Bambino
- Citizen Tsuyosa

## How We Chose

We looked for watches with strong reputations, dependable movements, and a clear
sense of identity — pieces that feel considered rather than generic.

## 1. Tissot PRX Quartz — the modern classic

**Best for:** readers who want a sharp, integrated-bracelet look without overspending

The PRX revived a 1970s design language and modernized it for daily wear. Its
fit and finish punch well above its price point. [Hodinkee](https://hodinkee.com)

## 2. Seiko 5 Sports — the dependable workhorse

**Best for:** first-time mechanical watch buyers who want reliability above all

Seiko's 5 Sports line has built a reputation for tough, no-fuss automatic movements
that keep ticking through years of daily wear. [Worn & Wound](https://wornandwound.com)

## 3. Hamilton Khaki Field Mechanical — the field-ready icon

**Best for:** buyers who want military heritage with genuine on-wrist presence

Hamilton's Khaki Field line draws on decades of military watch design, and the
hand-wound movement adds a tactile ritual that automatic wearers often miss.

## 4. Orient Bambino — the dress-watch sleeper hit

**Best for:** anyone who wants a domed-crystal dress watch on a budget

The Bambino's vintage-inspired case and dial proportions make it look far more
expensive than it is — a favorite among budget-minded collectors.

## 5. Citizen Tsuyosa — the modern minimalist

**Best for:** readers drawn to clean, contemporary integrated-bracelet designs

The Tsuyosa pairs a sunburst dial with a sharply finished bracelet, offering a
distinctly modern alternative to more vintage-styled options on this list.

## Buying or Choosing Tips

Compare bracelet fit, movement type, and overall proportions on your wrist before
deciding. Read a few independent reviews to see how each piece wears over time.

## Final Takeaway

Any of these five would make a satisfying daily watch — the right one comes down
to whether you favor vintage character, rugged simplicity, or modern polish.
"""

_DIRTY_PIPELINE_ARTICLE = """# 5 Best Automatic Watches Under $2000

This article uses a locked candidate pack and validated candidates from our query
contract. Each entry below reflects evidence-limited mode scoring.

## Quick Picks

- Tissot PRX Quartz
- Seiko 5 Sports

## 1. Tissot PRX Quartz

- **Source**: Not explicitly mentioned
- **Caveat**: evidence-limited; candidate_id=abc123

## 2. Seiko 5 Sports

- **Source**: Not explicitly mentioned
- **Caveat**: provided source excerpts did not fully validate this candidate_pack entry
"""

_REPEATED_PARAGRAPH_ARTICLE = """# Best Espresso Machines for Home Baristas

Choosing the right espresso machine can transform your morning routine into a
small daily ritual that you genuinely look forward to each day.

## Quick Picks

- Breville Barista Express
- Gaggia Classic Pro

## 1. Breville Barista Express

Choosing the right espresso machine can transform your morning routine into a
small daily ritual that you genuinely look forward to each day.

**Best for:** home baristas who want built-in grinding

## 2. Gaggia Classic Pro

**Best for:** purists who want a no-frills commercial-style machine

A reliable workhorse that has earned cult status among home enthusiasts for its
simplicity and upgrade potential.
"""

_GENERIC_FILLER_INTRO_ARTICLE = """# Best Productivity Apps for Students

In today's world, are you looking for the best productivity apps? Look no further!
In this article, we will cover everything you need to know about productivity apps
for students. Whether you're a high schooler or a graduate student juggling research
and deadlines, when it comes to staying organized, the right app can make all the
difference. Without further ado, let's dive into our picks and explore what makes
each one worth considering for your daily academic workflow and study routine today.

## Quick Picks

- Notion
- Todoist

## 1. Notion

**Best for:** students who want an all-in-one workspace

A flexible workspace that adapts to nearly any study system you throw at it.

## 2. Todoist

**Best for:** students who want a focused, no-nonsense task list

A clean task manager that stays out of your way while keeping deadlines visible.
"""

_MALFORMED_HEADING_ARTICLE = """# Best Tools

## Quick Picks

- Tool One
- Tool Two

## https://example.com/tool-one

**Best for:** people who like reading URLs as headings

Some text about tool one that is reasonably descriptive and useful for readers.

## $499

**Best for:** people who like prices as headings

Some text about tool two that is reasonably descriptive and useful for readers.
"""

_DUPLICATE_BEST_FOR_ARTICLE = """# Best Running Shoes

## Quick Picks

- Shoe One
- Shoe Two

## 1. Shoe One

**Best for:** runners who want comfort

A well-cushioned shoe that holds up over long distances and varied terrain types.

## 2. Shoe Two

**Best for:** runners who want comfort

Another shoe that performs well across a range of conditions and running styles.
"""

_LONG_HEADING_ARTICLE = """# Best Noise-Cancelling Headphones

## Quick Picks

- Headphone One
- Headphone Two

## 1. Headphone One — best pick for frequent travelers wanting long battery life and great comfort

**Best for:** frequent travelers who want long battery life and a comfortable fit

A genuinely impressive pair with strong noise cancellation and an easy-to-use companion app.

## 2. Headphone Two — a solid budget pick

**Best for:** listeners who want dependable performance without overspending

A reliable option that nails the basics without unnecessary extras or bloat.
"""

_LOW_BEST_FOR_COVERAGE_ARTICLE = """# Best Budget Laptops for Students

## Quick Picks

- Laptop One
- Laptop Two
- Laptop Three
- Laptop Four

## 1. Laptop One

**Best for:** students who want all-day battery life on a tight budget

A dependable everyday machine that handles note-taking and research without complaint.

## 2. Laptop Two

A capable machine with a sharp display and a keyboard that holds up to daily typing.

## 3. Laptop Three

Light enough to carry between classes and fast enough for everyday multitasking needs.

## 4. Laptop Four

A budget pick that trades some polish for a noticeably lower price tag than the rest.
"""


# ---------------------------------------------------------------------------
# Clean article scores well
# ---------------------------------------------------------------------------


def test_clean_recommendation_article_passes_with_high_score():
    result = run_article_quality_gate(
        _CLEAN_RECOMMENDATION_ARTICLE, is_recommendation=True, requested_count=5
    )
    assert isinstance(result, ArticleQualityGateResult)
    assert result.passes is True
    assert result.score >= 80
    assert result.publish_ceiling == "publish_ready"
    assert not any(d.severity == "high" for d in result.defects)


def test_clean_article_has_no_pipeline_language_defects():
    result = run_article_quality_gate(
        _CLEAN_RECOMMENDATION_ARTICLE, is_recommendation=True, requested_count=5
    )
    assert not any(d.type == "pipeline_language" for d in result.defects)


# ---------------------------------------------------------------------------
# Internal pipeline language detection
# ---------------------------------------------------------------------------


def test_pipeline_language_is_flagged_as_high_severity():
    result = run_article_quality_gate(
        _DIRTY_PIPELINE_ARTICLE, is_recommendation=True, requested_count=5
    )
    pipeline_defects = [d for d in result.defects if d.type == "pipeline_language"]
    assert pipeline_defects
    assert any(d.severity == "high" for d in pipeline_defects)
    assert result.passes is False
    assert result.publish_ceiling == "draft_only_not_publish_ready"


def test_source_not_explicitly_mentioned_lines_are_flagged():
    result = run_article_quality_gate(
        _DIRTY_PIPELINE_ARTICLE, is_recommendation=True, requested_count=5
    )
    assert any(
        "Source: Not explicitly mentioned" in d.message
        or "not explicitly mentioned" in d.message.lower()
        for d in result.defects
    )


def test_high_pipeline_language_score_caps_below_70():
    result = run_article_quality_gate(
        _DIRTY_PIPELINE_ARTICLE, is_recommendation=True, requested_count=5
    )
    assert result.score <= 69


# ---------------------------------------------------------------------------
# Structural defects
# ---------------------------------------------------------------------------


def test_repeated_paragraphs_are_flagged():
    result = run_article_quality_gate(
        _REPEATED_PARAGRAPH_ARTICLE, is_recommendation=True, requested_count=2
    )
    assert any(d.type == "repeated_paragraph" for d in result.defects)


def test_malformed_headings_are_flagged():
    result = run_article_quality_gate(
        _MALFORMED_HEADING_ARTICLE, is_recommendation=True, requested_count=2
    )
    malformed = [d for d in result.defects if d.type == "malformed_heading"]
    assert malformed
    assert malformed[0].severity == "high"
    assert result.publish_ceiling == "draft_only_not_publish_ready"


def test_generic_filler_intro_is_flagged():
    result = run_article_quality_gate(
        _GENERIC_FILLER_INTRO_ARTICLE, is_recommendation=True, requested_count=2
    )
    assert any(d.type == "generic_intro" for d in result.defects)


def test_clean_article_intro_not_flagged_as_generic():
    result = run_article_quality_gate(
        _CLEAN_RECOMMENDATION_ARTICLE, is_recommendation=True, requested_count=5
    )
    assert not any(d.type == "generic_intro" for d in result.defects)


# ---------------------------------------------------------------------------
# Recommendation-specific checks
# ---------------------------------------------------------------------------


def test_duplicate_best_for_is_flagged():
    result = run_article_quality_gate(
        _DUPLICATE_BEST_FOR_ARTICLE, is_recommendation=True, requested_count=2
    )
    assert any(d.type == "duplicate_best_for" for d in result.defects)


def test_long_heading_over_90_chars_is_flagged():
    result = run_article_quality_gate(
        _LONG_HEADING_ARTICLE, is_recommendation=True, requested_count=2
    )
    long_headings = [d for d in result.defects if d.type == "long_heading"]
    assert long_headings
    assert long_headings[0].severity == "low"


def test_clean_article_has_no_long_heading_defect():
    result = run_article_quality_gate(
        _CLEAN_RECOMMENDATION_ARTICLE, is_recommendation=True, requested_count=5
    )
    assert not any(d.type == "long_heading" for d in result.defects)


def test_low_best_for_coverage_is_flagged():
    """Fewer than 70% of recommendation sections have a 'Best for' entry."""
    result = run_article_quality_gate(
        _LOW_BEST_FOR_COVERAGE_ARTICLE, is_recommendation=True, requested_count=4
    )
    missing_best_for = [d for d in result.defects if d.type == "missing_best_for"]
    assert missing_best_for
    assert missing_best_for[0].severity == "medium"
    assert "1/4" in missing_best_for[0].message


def test_clean_article_meets_best_for_coverage_threshold():
    """The clean fixture has a 'Best for' on every pick — no coverage defect."""
    result = run_article_quality_gate(
        _CLEAN_RECOMMENDATION_ARTICLE, is_recommendation=True, requested_count=5
    )
    assert not any(d.type == "missing_best_for" for d in result.defects)


def test_missing_quick_picks_is_high_severity():
    article = "# Best Things\n\nSome intro text.\n\n## How We Chose\n\nReasons go here.\n"
    result = run_article_quality_gate(article, is_recommendation=True, requested_count=3)
    missing = [d for d in result.defects if d.type == "missing_quick_picks"]
    assert missing
    assert missing[0].severity == "high"
    assert result.publish_ceiling == "draft_only_not_publish_ready"


def test_count_mismatch_without_framing_is_flagged():
    article = (
        "# Best Things\n\n"
        "An interesting and specific opening about these particular picks and why "
        "they matter to readers looking for solid options today.\n\n"
        "## Quick Picks\n\n- Thing One\n- Thing Two\n\n"
        "## How We Chose\n\nWe picked carefully based on real-world performance.\n"
    )
    result = run_article_quality_gate(article, is_recommendation=True, requested_count=5)
    assert any(d.type == "count_mismatch" for d in result.defects)


def test_count_mismatch_with_natural_framing_is_not_flagged():
    article = (
        "# 2 Standout Picks for This Category\n\n"
        "After reviewing the leading options, two stood out clearly above the rest "
        "for their consistency and reputation among real users.\n\n"
        "## Quick Picks\n\n- Thing One\n- Thing Two\n\n"
        "## How We Chose\n\nWe focused on reputation, durability, and everyday fit "
        "rather than chasing a longer list for its own sake.\n"
    )
    result = run_article_quality_gate(article, is_recommendation=True, requested_count=5)
    assert not any(d.type == "count_mismatch" for d in result.defects)


# ---------------------------------------------------------------------------
# Non-recommendation articles skip recommendation-specific checks
# ---------------------------------------------------------------------------


def test_non_recommendation_article_skips_recommendation_checks():
    article = (
        "# Understanding Quantum Computing\n\n"
        "Quantum computing uses principles of superposition and entanglement to "
        "process information differently than classical computers.\n\n"
        "## Background\n\nThe field traces its roots to the early 1980s.\n\n"
        "## Key Concepts\n\nQubits can represent multiple states simultaneously.\n\n"
        "## Conclusion\n\nThe field continues to evolve rapidly.\n"
    )
    result = run_article_quality_gate(article, is_recommendation=False)
    assert not any(d.type == "missing_quick_picks" for d in result.defects)
    assert not any(d.type == "duplicate_best_for" for d in result.defects)
    assert not any(d.type == "count_mismatch" for d in result.defects)


# ---------------------------------------------------------------------------
# Score / ceiling invariants
# ---------------------------------------------------------------------------


def test_score_is_bounded_between_0_and_100():
    for article in (
        _CLEAN_RECOMMENDATION_ARTICLE,
        _DIRTY_PIPELINE_ARTICLE,
        _REPEATED_PARAGRAPH_ARTICLE,
        _GENERIC_FILLER_INTRO_ARTICLE,
        _MALFORMED_HEADING_ARTICLE,
        _DUPLICATE_BEST_FOR_ARTICLE,
    ):
        result = run_article_quality_gate(article, is_recommendation=True, requested_count=2)
        assert 0 <= result.score <= 100


def test_high_defects_force_draft_only_ceiling():
    result = run_article_quality_gate(
        _MALFORMED_HEADING_ARTICLE, is_recommendation=True, requested_count=2
    )
    high = [d for d in result.defects if d.severity == "high"]
    assert high
    assert result.publish_ceiling == "draft_only_not_publish_ready"
    assert result.passes is False


def test_passes_requires_score_at_least_80_and_no_high_defects():
    result = run_article_quality_gate(
        _CLEAN_RECOMMENDATION_ARTICLE, is_recommendation=True, requested_count=5
    )
    assert result.score >= 80
    assert not any(d.severity == "high" for d in result.defects)
    assert result.passes is True
