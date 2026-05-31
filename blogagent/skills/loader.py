"""Deterministic skill selection based on topic intent.

Skill selection is fully deterministic — no LLM, no I/O.
Selected skills are stored in state.selected_skills and injected into
agent prompts as concise editorial briefs.
"""

from __future__ import annotations

_FRAGRANCE_KEYWORDS: frozenset[str] = frozenset(
    {
        "perfume",
        "parfum",
        "fragrance",
        "cologne",
        "scent",
        "eau de",
    }
)

_LIFESTYLE_KEYWORDS: frozenset[str] = frozenset(
    {
        "beauty",
        "fashion",
        "lifestyle",
        "fragrance",
        "makeup",
        "skincare",
        "perfume",
        "parfum",
        "cologne",
        "scent",
    }
)


def select_skills(
    topic: str,
    is_recommendation: bool,
    is_financial: bool,
) -> list[str]:
    """Return the ordered list of skill names to load for this topic."""
    topic_lower = topic.lower()

    is_fragrance = any(kw in topic_lower for kw in _FRAGRANCE_KEYWORDS)
    is_lifestyle = any(kw in topic_lower for kw in _LIFESTYLE_KEYWORDS)

    if is_financial:
        return [
            "financial-safety",
            "source-quality-assessment",
            "citation-grounding",
            "seo-blog-writing",
            "editorial-revision",
            "personal-blog-voice",
            "publishability-review",
        ]

    if is_recommendation:
        skills = [
            "recommendation-writing",
            "source-quality-assessment",
            "citation-grounding",
            "product-recommendation-depth",
            "seo-blog-writing",
            "editorial-revision",
            "personal-blog-voice",
            "publishability-review",
        ]
        if is_fragrance:
            skills.insert(1, "beauty-fragrance-writing")
        if is_lifestyle and not is_fragrance:
            skills.insert(1, "fashion-lifestyle-editorial")
        return skills

    if is_lifestyle:
        return [
            "fashion-lifestyle-editorial",
            "citation-grounding",
            "seo-blog-writing",
            "personal-blog-voice",
            "publishability-review",
        ]

    return [
        "citation-grounding",
        "seo-blog-writing",
        "personal-blog-voice",
        "publishability-review",
    ]
