"""Recommendation candidate extractor.

Extracts named product/entity candidates from evidence items,
scores each for usability, and captures nearby sensory/contextual detail.

Permission class: read_only
All operations are deterministic — no LLM calls.

A usable recommendation candidate requires:
  - named product/entity
  - appears in a high or medium quality source, OR in 2+ sources
  - has at least one supporting context or sensory term
Low-quality-only single-source mentions are marked low_confidence and not usable.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel

from blogagent.workflow.state import EvidenceItem

# ---------------------------------------------------------------------------
# Sensory / context term lists
# ---------------------------------------------------------------------------

_SCENT_TERMS: frozenset[str] = frozenset(
    {
        "notes",
        "base note",
        "top note",
        "heart note",
        "sillage",
        "longevity",
        "projection",
        "dry down",
        "scent family",
        "floral",
        "woody",
        "oriental",
        "fresh",
        "citrus",
        "musk",
        "amber",
        "oud",
        "spicy",
        "sweet",
        "powdery",
        "aquatic",
        "green",
        "leather",
        "sandalwood",
        "vetiver",
        "neroli",
        "rose",
        "jasmine",
        "orange blossom",
        "bergamot",
        "vanilla",
        "patchouli",
        "iris",
        "coconut",
        "marine",
        "clean",
        "earthy",
        "fruity",
        "musky",
        "smoky",
    }
)

_SUITABILITY_TERMS: frozenset[str] = frozenset(
    {
        "summer",
        "heat",
        "warm weather",
        "date night",
        "long-lasting",
        "budget",
        "overall",
        "chic",
        "light",
        "beach",
        "evening",
        "tested",
        "reviewed",
        "editor",
        "expert",
        "best for",
        "perfect for",
        "ideal for",
        "great for",
        "recommended",
        "award",
        "classic",
        "signature",
        "everyday",
        "office",
        "spring",
        "fall",
        "winter",
        "casual",
        "romantic",
        "daytime",
        "nighttime",
        "all-day",
        "office-friendly",
        "summer heat",
        "warm-weather",
    }
)

# Stop-words that are never product names on their own
_STOP_WORDS: frozenset[str] = frozenset(
    {
        "the",
        "a",
        "an",
        "this",
        "that",
        "these",
        "those",
        "and",
        "or",
        "but",
        "with",
        "for",
        "from",
        "into",
        "onto",
        "about",
        "over",
        "under",
        "after",
        "before",
        "between",
        "during",
        "without",
        "through",
        "by",
        "at",
        "to",
        "in",
        "of",
        "our",
        "your",
        "their",
        "its",
        "all",
        "most",
        "some",
        "any",
        "when",
        "where",
        "which",
        "who",
        "what",
        "how",
        "if",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "shall",
        "can",
        "best",
        "top",
        "good",
        "great",
        "well",
        "new",
        "old",
        "first",
        "last",
        "more",
        "most",
        "less",
        "few",
        "many",
        "much",
        "very",
        "too",
        "also",
        "just",
        "so",
        "then",
        "than",
        "other",
        "another",
        "each",
        "every",
        "here",
        "there",
        "now",
        "as",
        "us",
        "we",
        "it",
        "he",
        "she",
        "they",
    }
)

# Known brand prefixes for beauty/fragrance/lifestyle
_BRAND_PREFIXES: tuple[str, ...] = (
    "chanel",
    "dior",
    "gucci",
    "ysl",
    "yves saint laurent",
    "tom ford",
    "lancôme",
    "lancome",
    "armani",
    "versace",
    "burberry",
    "givenchy",
    "marc jacobs",
    "jo malone",
    "byredo",
    "le labo",
    "diptyque",
    "maison margiela",
    "aesop",
    "mugler",
    "hermes",
    "hermès",
    "prada",
    "valentino",
    "dolce & gabbana",
    "bulgari",
    "bvlgari",
    "calvin klein",
    "ralph lauren",
    "hugo boss",
    "clarins",
    "nars",
    "mac ",
    "charlotte tilbury",
    "rare beauty",
    "fenty beauty",
    "ouai",
    "olaplex",
    "cetaphil",
    "cerave",
    "la roche-posay",
    "tatcha",
    "drunk elephant",
    "paula's choice",
)

# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------


class RecommendationCandidate(BaseModel):
    name: str
    source_urls: list[str]
    source_quality: Literal["high", "medium", "low"]
    supported_context: list[str]
    sensory_terms: list[str]
    usable: bool
    reason: str
    low_confidence: bool = False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_recommendations_from_evidence(
    evidence_items: list[EvidenceItem],
    source_quality_scores: list[dict],
    topic: str = "",
) -> list[RecommendationCandidate]:
    """Extract named recommendation candidates from evidence items.

    Returns candidates with source quality, context, and usability data.
    Mock/placeholder evidence yields no candidates — correct for mock mode.
    """
    quality_map: dict[str, str] = {
        sq.get("url", ""): sq.get("quality", "medium")
        for sq in source_quality_scores
        if sq.get("url")
    }

    # Accumulate per-name data across all evidence items
    name_data: dict[str, dict] = {}

    for item in evidence_items:
        if _is_placeholder(item.fact):
            continue

        quality = quality_map.get(item.source_url, "medium")
        names = _extract_names_from_text(item.fact)
        sensory = _extract_scent_terms(item.fact)
        context = _extract_context_terms(item.fact)

        for name in names:
            if name not in name_data:
                name_data[name] = {
                    "source_urls": [],
                    "source_quality": quality,
                    "sensory_terms": set(),
                    "supported_context": set(),
                }
            entry = name_data[name]
            if item.source_url not in entry["source_urls"]:
                entry["source_urls"].append(item.source_url)
            # Upgrade quality if this source is better
            if quality == "high":
                entry["source_quality"] = "high"
            elif quality == "medium" and entry["source_quality"] == "low":
                entry["source_quality"] = "medium"
            entry["sensory_terms"].update(sensory)
            entry["supported_context"].update(context)

    candidates: list[RecommendationCandidate] = []
    for name, data in name_data.items():
        source_quality: Literal["high", "medium", "low"] = data["source_quality"]
        is_low_confidence = source_quality == "low" and len(data["source_urls"]) < 2
        usable, reason = _decide_usable(
            source_quality=source_quality,
            supported_context=list(data["supported_context"]),
            sensory_terms=list(data["sensory_terms"]),
            is_low_confidence=is_low_confidence,
        )
        candidates.append(
            RecommendationCandidate(
                name=name,
                source_urls=data["source_urls"],
                source_quality=source_quality,
                supported_context=sorted(data["supported_context"]),
                sensory_terms=sorted(data["sensory_terms"]),
                usable=usable,
                reason=reason,
                low_confidence=is_low_confidence,
            )
        )

    return candidates


def build_candidates_summary(candidates: list[RecommendationCandidate]) -> dict:
    """Build a compact summary dict safe for API responses."""
    usable = [c for c in candidates if c.usable]
    low_conf = [c for c in candidates if c.low_confidence]
    return {
        "usable_count": len(usable),
        "low_confidence_count": len(low_conf),
        "names": [c.name for c in usable],
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_placeholder(text: str) -> bool:
    if not text or len(text.strip()) < 20:
        return True
    lower = text.lower().strip()
    return (
        lower.startswith("information about")
        or "lorem ipsum" in lower
        or "[placeholder" in lower
        or "[insert" in lower
    )


def _extract_names_from_text(text: str) -> list[str]:
    """Extract candidate product/brand names from a text snippet."""
    found: list[str] = []

    # Bold markdown: **Brand Name**
    for m in re.finditer(r"\*\*([A-Z][^*\n]{2,50})\*\*", text):
        name = m.group(1).strip(" .,;:")
        if _looks_like_product_name(name):
            found.append(name)

    # Numbered list: "1. Brand Name"  or "1) Brand Name"
    for m in re.finditer(
        r"^\s*\d+[.)]\s+([A-Z][^\n—–\-:,]{2,60}?)(?:\s*[—–\-:]|\s*$)",
        text,
        re.MULTILINE,
    ):
        name = m.group(1).strip(" .,;:")
        if _looks_like_product_name(name):
            found.append(name)

    # Bullet list: "- Brand Name" or "* Brand Name"
    for m in re.finditer(
        r"^\s*[-*•]\s+([A-Z][^\n—–:,]{2,60}?)(?:\s*[—–:]|\s*$)",
        text,
        re.MULTILINE,
    ):
        name = m.group(1).strip(" .,;:")
        if _looks_like_product_name(name):
            found.append(name)

    # Known brand prefix scan: "Chanel Chance Eau Tendre ..."
    lower = text.lower()
    for prefix in _BRAND_PREFIXES:
        idx = lower.find(prefix)
        if idx == -1:
            continue
        # Capture up to 6 words starting from brand prefix in original case
        raw = text[idx : idx + 80]
        tokens = raw.split()[:6]
        candidate = " ".join(t.strip(".,;:!?\"'()") for t in tokens).strip()
        # Trim trailing stop words from the candidate
        candidate_words = candidate.split()
        while candidate_words and candidate_words[-1].lower() in _STOP_WORDS:
            candidate_words.pop()
        candidate = " ".join(candidate_words)
        if _looks_like_product_name(candidate):
            found.append(candidate)

    # Deduplicate preserving order; prefer longer/more specific names
    seen: set[str] = set()
    result: list[str] = []
    for name in found:
        key = name.lower().strip()
        if key not in seen and len(name) >= 4:
            seen.add(key)
            result.append(name)

    return result


def _looks_like_product_name(name: str) -> bool:
    """Return True if the string looks like a product/brand name."""
    name = name.strip()
    if len(name) < 3 or len(name) > 80:
        return False
    words = name.split()
    # Must have at least one capitalized word
    if not any(w and w[0].isupper() for w in words):
        return False
    # Must have at least one non-stop-word token
    clean = [w.lower().strip(".,;:!?\"'") for w in words]
    meaningful = [w for w in clean if w and w not in _STOP_WORDS]
    if not meaningful:
        return False
    # Reject strings that start with common generic heading words
    lower = name.lower()
    for skip in (
        "how to",
        "why ",
        "what ",
        "when ",
        "the best",
        "introduction",
        "overview",
        "conclusion",
        "section",
        "part ",
        "chapter ",
    ):
        if lower.startswith(skip):
            return False
    return True


def _extract_scent_terms(text: str) -> list[str]:
    lower = text.lower()
    return [t for t in _SCENT_TERMS if t in lower]


def _extract_context_terms(text: str) -> list[str]:
    lower = text.lower()
    return [t for t in _SUITABILITY_TERMS if t in lower]


def _decide_usable(
    source_quality: str,
    supported_context: list[str],
    sensory_terms: list[str],
    is_low_confidence: bool,
) -> tuple[bool, str]:
    if is_low_confidence:
        return False, "Low-quality source only (single source) — not usable as core pick"
    has_context = bool(supported_context) or bool(sensory_terms)
    if source_quality in ("high", "medium"):
        if has_context:
            return True, (
                f"Named in {source_quality}-quality source with "
                f"{len(supported_context)} context / {len(sensory_terms)} sensory term(s)"
            )
        # High/medium source, no context — weakly usable
        return True, f"Named in {source_quality}-quality source (limited supporting detail)"
    # Low quality but multi-source
    if has_context:
        return True, "Named in multiple sources with supporting context (low-quality only)"
    return False, "Low-quality sources only with no supporting context"
