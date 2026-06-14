from __future__ import annotations

from blogagent.tools.article_presentation import (
    get_publish_status_label,
    get_visible_article_markdown,
    is_evidence_report_article,
)


def test_publish_status_labels_map_internal_enums_to_user_facing_text():
    assert get_publish_status_label("publish_ready") == "Copy-ready"
    assert (
        get_publish_status_label("publish_ready_with_editorial_review")
        == "Copy-ready after light review"
    )
    assert (
        get_publish_status_label("draft_only_not_publish_ready") == "Needs revision before use"
    )


def test_evidence_report_article_gets_its_own_label_regardless_of_status():
    markdown = "# Evidence Report: Draft Only\n\n## What Was Searched\n\n..."
    assert is_evidence_report_article(markdown)
    assert (
        get_publish_status_label("draft_only_not_publish_ready", markdown)
        == "Evidence report — not a blog draft"
    )


def test_non_evidence_report_article_is_not_mislabeled():
    markdown = "# 5 Best Affordable Luxury Watches: Our Picks\n\n## Quick Picks\n\n- Tissot PRX"
    assert not is_evidence_report_article(markdown)
    assert get_publish_status_label("publish_ready", markdown) == "Copy-ready"


def test_visible_article_card_excludes_debug_blocks():
    markdown = (
        "# 5 Best Affordable Luxury Watches: Our Picks\n"
        "<!-- Tone: Personal Blog -->\n\n"
        "## Quick Picks\n\n"
        "- Tissot PRX Quartz\n"
    )
    visible = get_visible_article_markdown(markdown)
    assert "<!--" not in visible
    assert "Tone: Personal Blog" not in visible
    assert "# 5 Best Affordable Luxury Watches: Our Picks" in visible
    assert "## Quick Picks" in visible
    assert "- Tissot PRX Quartz" in visible


def test_visible_article_markdown_unchanged_when_no_debug_blocks():
    markdown = "# How to Choose a Summer Perfume\n\n## Introduction\n\nSome text."
    assert get_visible_article_markdown(markdown) == markdown
