"""Presentation helpers for translating pipeline output into user-facing UI text.

Permission class: read_only

Internal status enums (``publish_ready_status`` values, candidate pack modes,
etc.) are used throughout the workflow, persistence, and tests and must not
change. This module is the single place where those internal values are
mapped to the short labels shown to a user in the UI, and where the visible
article markdown is separated from internal authoring/debug markers.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Publish status labels
# ---------------------------------------------------------------------------

_PUBLISH_STATUS_LABELS: dict[str, str] = {
    "publish_ready": "Copy-ready",
    "publish_ready_with_editorial_review": "Copy-ready after light review",
    "publish_ready_with_warnings": "Copy-ready after light review",
    "draft_only_not_publish_ready": "Needs revision before use",
}

_EVIDENCE_REPORT_LABEL = "Evidence report — not a blog draft"


def is_evidence_report_article(article_markdown: str) -> bool:
    """Return True if the article is a deterministic Evidence Report, not a blog draft."""
    if not article_markdown:
        return False
    first_line = article_markdown.strip().splitlines()[0]
    return first_line.startswith("# Evidence Report")


def get_publish_status_label(publish_ready_status: str, article_markdown: str = "") -> str:
    """Map an internal ``publish_ready_status`` value to a user-facing label.

    The internal enum value passed in (and stored/persisted elsewhere) is
    unchanged — this only controls the text shown to the user. Evidence
    Report output (the finance/below-minimum fallback) always gets its own
    label regardless of the underlying status, since it is not a blog draft.
    """
    if is_evidence_report_article(article_markdown):
        return _EVIDENCE_REPORT_LABEL
    return _PUBLISH_STATUS_LABELS.get(publish_ready_status, publish_ready_status)


# ---------------------------------------------------------------------------
# Visible article markdown vs. internal/debug markers
# ---------------------------------------------------------------------------

# HTML-comment-only lines (e.g. "<!-- Tone: Personal Blog -->") are internal
# authoring annotations and must never reach the copy-paste-ready article.
_DEBUG_COMMENT_LINE_RE = re.compile(r"^[ \t]*<!--.*-->[ \t]*\n?", re.MULTILINE)


def get_visible_article_markdown(article_markdown: str) -> str:
    """Return the article markdown with internal/debug-only lines removed.

    Currently strips standalone HTML comment lines (authoring annotations
    such as tone markers). Everything else is left untouched so the visible
    article card always matches what the user can copy and paste.
    """
    if not article_markdown:
        return article_markdown
    cleaned = _DEBUG_COMMENT_LINE_RE.sub("", article_markdown)
    # Collapse blank-line runs left behind by stripped comment lines.
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()
