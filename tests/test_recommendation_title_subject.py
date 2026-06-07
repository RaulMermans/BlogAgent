"""Regression tests for recommendation-article title generation.

Manual QA on a live pipeline run surfaced a real "the article itself isn't
good enough" defect: for topics phrased as "a casual guide to the top 5
summer fragrances", the title generator naively prefixed "{count} Best
{topic}: Our Picks" onto the *entire* topic string (which already contained
its own "guide to the top 5" framing), producing a doubled, nonsensical
title:

    "5 Best A Casual Guide To The Top 5 Summer Fragrances: Our Picks"

No automated gate caught this — it's schema-valid, has no pipeline language,
no repeated paragraphs, and a well-formed heading. Only reading the actual
rendered title revealed it. These tests pin the fix: `_recommendation_subject`
must strip both "leading count" framing ("5 best X") and "guide to the top N"
framing ("a casual guide to the top 5 X"), leaving a clean bare subject that
title generation can build on without doubling up.
"""

from __future__ import annotations

from blogagent.agents.editor_agent import (
    _editorial_recommendation_title,
    _recommendation_subject,
    _standard_recommendation_title,
)


def test_subject_strips_leading_count_qualifier():
    assert _recommendation_subject("5 best automatic watches under $2000") == (
        "automatic watches under $2000"
    )


def test_subject_strips_leading_top_count():
    assert _recommendation_subject("Top 10 gadgets of 2024") == "gadgets of 2024"


def test_subject_strips_guide_to_framing_with_embedded_count():
    """The exact phrasing that produced the doubled-title bug found via manual QA."""
    subject = _recommendation_subject("A casual guide to the top 5 summer fragrances")
    assert subject == "summer fragrances"
    assert "guide" not in subject.lower()
    assert "5" not in subject


def test_subject_strips_guide_to_framing_count_after_guide():
    subject = _recommendation_subject("guide to the 5 best budget headphones")
    assert subject == "budget headphones"


def test_subject_with_no_count_or_framing_is_left_intact():
    assert _recommendation_subject("Best AI tools for students") == "Best AI tools for students"


def test_editorial_title_for_guide_phrasing_is_not_doubled():
    title = _editorial_recommendation_title(5, "A casual guide to the top 5 summer fragrances")
    assert title == "5 Best Summer Fragrances: Our Picks"
    # The defect we're guarding against: the raw framing words leaking into the title.
    assert "Guide" not in title
    assert "Casual" not in title
    assert title.count("5") == 1


def test_standard_title_for_guide_phrasing_is_not_doubled():
    title = _standard_recommendation_title(5, "A casual guide to the top 5 summer fragrances")
    assert title == "5 Best summer fragrances"
    assert "Guide" not in title
    assert "Casual" not in title
    assert title.count("5") == 1


def test_editorial_title_for_simple_leading_count_topic_is_clean():
    title = _editorial_recommendation_title(5, "5 best automatic watches under $2000")
    assert title == "5 Best Automatic Watches Under $2000: Our Picks"


def test_standard_title_for_simple_leading_count_topic_is_clean():
    title = _standard_recommendation_title(7, "7 best perfumes for summer")
    assert title == "7 Best perfumes for summer"
