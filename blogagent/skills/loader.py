"""Deterministic skill selection based on topic intent.

Skill selection is fully deterministic — no LLM, no I/O.
Selected skills are stored in state.selected_skills and injected into
agent prompts as concise editorial briefs.
"""

from __future__ import annotations


def select_skills(
    topic: str,  # noqa: ARG001 — reserved for future topic-level heuristics
    is_recommendation: bool,
    is_financial: bool,
) -> list[str]:
    """Return the ordered list of skill names to load for this topic."""
    if is_recommendation:
        return [
            "recommendation-writing",
            "source-quality-assessment",
            "citation-grounding",
            "seo-blog-writing",
            "editorial-revision",
        ]
    if is_financial:
        return [
            "financial-safety",
            "source-quality-assessment",
            "citation-grounding",
            "seo-blog-writing",
            "editorial-revision",
        ]
    return [
        "citation-grounding",
        "seo-blog-writing",
    ]
