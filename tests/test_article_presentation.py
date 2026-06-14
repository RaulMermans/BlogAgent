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


def test_status_label_mapping():
    """Every internal publish_ready_status enum value maps to a user-facing label."""
    assert get_publish_status_label("publish_ready") == "Copy-ready"
    assert (
        get_publish_status_label("publish_ready_with_editorial_review")
        == "Copy-ready after light review"
    )
    assert (
        get_publish_status_label("publish_ready_with_warnings") == "Copy-ready after light review"
    )
    assert get_publish_status_label("draft_only_not_publish_ready") == "Needs revision before use"


def test_visible_ui_uses_copy_ready_language():
    """User-facing labels use copy-ready language, never raw snake_case enum values."""
    for status in (
        "publish_ready",
        "publish_ready_with_editorial_review",
        "publish_ready_with_warnings",
        "draft_only_not_publish_ready",
    ):
        label = get_publish_status_label(status)
        assert "_" not in label
        assert label != status
        assert "ready" in label.lower() or "revision" in label.lower()


def test_debug_can_show_internal_status_but_article_card_cannot():
    """A debug-only annotation containing the raw internal status enum is stripped
    from the visible article card but remains in the raw markdown available to
    debug views."""
    raw_status = "publish_ready_with_editorial_review"
    markdown = (
        "# 5 Best Affordable Luxury Watches: Our Picks\n"
        f"<!-- publish_ready_status: {raw_status} -->\n\n"
        "## Quick Picks\n\n"
        "- Tissot PRX Quartz\n"
    )
    # Debug views see the raw markdown, including the internal enum value.
    assert raw_status in markdown

    # The visible article card strips debug annotations entirely.
    visible = get_visible_article_markdown(markdown)
    assert raw_status not in visible
    assert "publish_ready_status" not in visible
