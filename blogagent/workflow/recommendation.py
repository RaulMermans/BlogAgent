"""Recommendation topic detection and related guardrails.

All functions are deterministic — no LLM calls, no I/O side effects.
"""

from __future__ import annotations

import os
import re

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


_WORD_NUMBERS: dict[str, int] = {
    "twenty": 20,
    "fifteen": 15,
    "twelve": 12,
    "eleven": 11,
    "ten": 10,
    "nine": 9,
    "eight": 8,
    "seven": 7,
    "six": 6,
    "five": 5,
    "four": 4,
    "three": 3,
    "two": 2,
    "one": 1,
}


def normalize_number_words(text: str) -> str:
    """Replace English number words with digits (longest first to avoid partial matches)."""
    result = text
    for word, num in _WORD_NUMBERS.items():
        result = re.sub(rf"\b{word}\b", str(num), result, flags=re.IGNORECASE)
    return result


def _is_year_or_price(n: int, text_lower: str) -> bool:
    """Return True if n looks like a year or price context, not a list count."""
    if 1900 <= n <= 2099:
        return True
    if re.search(
        rf"\b(?:under|over|below|above|less\s+than|more\s+than|\$)\s*{n}\b",
        text_lower,
    ):
        return True
    if re.search(rf"\b{n}\s*(?:dollars?|usd|euros?|pounds?|€|\$)\b", text_lower):
        return True
    if re.search(rf"\b(?:for)\s+{n}\s+(?:people|persons?|guests?|users?)\b", text_lower):
        return True
    return False


def extract_requested_count(topic: str) -> "int | None":
    """Extract an explicit item count from the topic string.

    Handles patterns like:
      '7 best parfums for summer' → 7
      'seven best perfumes' → 7
      'top 10 perfumes' → 10
      'best 5 options' → 5
      'top ten picks' → 10
      'a list of 7 perfumes' → 7
      'recommend 5 summer fragrances' → 5
      'give me five options' → 5

    False-positive guards prevent matching years (2025) and prices (under $50).
    Returns None if no explicit count is stated.
    """
    # Normalize word numbers first so all branches only handle digits
    normalized = normalize_number_words(topic)
    lower = normalized.lower()

    # Pattern 1: ranking keyword BEFORE digit — "top 10", "best 7"
    m = re.search(r"\b(?:top|best|recommended?)\s+(\d+)\b", lower)
    if m:
        n = int(m.group(1))
        if not _is_year_or_price(n, lower):
            return n

    # Pattern 2: digit BEFORE ranking keyword — "7 best", "10 top"
    m = re.search(r"\b(\d+)\s+(?:top|best|recommended?)\b", lower)
    if m:
        n = int(m.group(1))
        if not _is_year_or_price(n, lower):
            return n

    # Pattern 3: list/suggest context — "a list of 7", "give me 5", "recommend 5"
    m = re.search(
        r"\b(?:(?:a\s+)?list\s+of|give\s+me|show\s+me|find\s+me|suggest|recommend)\s+(\d+)\b",
        lower,
    )
    if m:
        n = int(m.group(1))
        if not _is_year_or_price(n, lower):
            return n

    return None
