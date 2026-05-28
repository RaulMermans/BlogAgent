"""Recommendation topic detection and related guardrails.

All functions are deterministic — no LLM calls, no I/O side effects.
"""

from __future__ import annotations

import os

# Keywords (as substrings of topic.lower()) that indicate the user wants a
# curated list or ranking of specific products, services, or entities.
_RECOMMENDATION_KEYWORDS: frozenset[str] = frozenset(
    {
        "best",
        "top",
        "recommended",
        "recommendations",
        "products",
        "perfumes",
        "parfums",
        "fragrances",
        "makeup",
        "skincare",
        "tools",
        "laptops",
        "shoes",
        "restaurants",
        "hotels",
        "stocks",
        "invest",
        "current",
        "recent",
        "2025",
        "2026",
    }
)

# Subset indicating financial / investment content that requires a disclaimer.
_FINANCIAL_KEYWORDS: frozenset[str] = frozenset(
    {
        "stocks",
        "invest",
        "investment",
        "crypto",
        "trading",
    }
)

MOCK_RECOMMENDATION_WARNING = (
    "Real search is required for recommendation or current-product topics. "
    "This article will not include specific named product recommendations — "
    "enable Tavily search (BLOGAGENT_SEARCH_PROVIDER=tavily) and a real LLM "
    "provider for source-grounded recommendations."
)

FINANCIAL_DISCLAIMER_WARNING = (
    "This topic involves financial or investment content. "
    "The article is framed as an educational overview only — not financial advice. "
    "Do not make financial decisions based on this content."
)


def is_recommendation_topic(topic: str) -> bool:
    """Return True if the topic requests a recommendation, ranking, or product list."""
    lower = topic.lower()
    return any(kw in lower for kw in _RECOMMENDATION_KEYWORDS)


def is_financial_topic(topic: str) -> bool:
    """Return True if the topic involves financial or investment content."""
    lower = topic.lower()
    return any(kw in lower for kw in _FINANCIAL_KEYWORDS)


def is_real_search_active() -> bool:
    """Return True if a real (non-mock) search provider is configured via env var."""
    provider = os.getenv("BLOGAGENT_SEARCH_PROVIDER", "mock").strip().lower()
    return provider != "mock"


def extract_requested_count(topic: str) -> "int | None":
    """Extract an explicit item count from the topic string.

    Recognises patterns like 'top 10', 'best 5', 'top five', 'best ten'.
    Returns None if no explicit count is stated.
    """
    import re  # noqa: PLC0415

    lower = topic.lower()

    # Numeric: "top 10", "best 5"
    m = re.search(r"\b(?:top|best)\s+(\d+)\b", lower)
    if m:
        return int(m.group(1))

    # Word numbers: "top five", "best ten"
    _WORD_NUMBERS = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
        "eleven": 11,
        "twelve": 12,
        "fifteen": 15,
        "twenty": 20,
    }
    for word, val in _WORD_NUMBERS.items():
        if re.search(rf"\b(?:top|best)\s+{word}\b", lower):
            return val

    return None
