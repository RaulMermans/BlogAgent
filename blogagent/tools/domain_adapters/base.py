"""Base domain adapter — provides universal rejection rules.

All domain adapters inherit from this class. Override methods to add
domain-specific logic. The base adapter is used for the "general" domain
and as a fallback for unknown domains.

Permission class: read_only
All operations are deterministic — no LLM calls.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from blogagent.workflow.query_contract import QueryContract

# ---------------------------------------------------------------------------
# Universal rejection sets — shared across all domains
# ---------------------------------------------------------------------------

_SECTION_HEADING_PHRASES: frozenset[str] = frozenset(
    {
        "how we chose",
        "how we tested",
        "buying tips",
        "buying or choosing tips",
        "buying guide",
        "final takeaway",
        "conclusion",
        "sources",
        "references",
        "citations",
        "further reading",
        "introduction",
        "overview",
        "about",
        "summary",
        "key takeaways",
        "editor's note",
        "methodology",
        "what to look for",
        "faq",
        "frequently asked questions",
        "the bottom line",
        "our top",
        "choosing your",
        "recommendations",
        "guide",
        "quick picks",
        "top picks",
        "our picks",
        "best options",
        "candidates found",
    }
)

_SECTION_HEADING_SUBSTRINGS: tuple[str, ...] = (
    "how we chose",
    "how we tested",
    "quick picks",
    "our top",
    "choosing your",
    "final takeaway",
    "buying tips",
    "buying or choosing tips",
    "conclusion",
    "introduction",
    "sources",
    "guide",
    "recommendations",
    "best options",
    "top picks",
    "our picks",
    "candidates found",
    # Editorial heading patterns that appear as H2/H3 in recommendation articles
    "navigating",
    "spotlight on",
    "our approach",
    "the shifting",
    "opportunities in",
    "players for",
    "landscape for",
    "identifying energy",
    "identifying ai",
    "key energy",
    "key ai",
    "for student success",
)

_SOURCE_ARTIFACT_PATTERNS: tuple[str, ...] = (
    "http://",
    "https://",
    ".com",
    ".org",
    ".net",
    ".co",
)

_CITATION_PATTERNS = re.compile(r"^\[?\d+\]?$|^\(\d+\)$")


class DomainAdapter:
    """Base domain adapter with universal rejection rules."""

    domain: str = "general"

    # ---------------------------------------------------------------------------
    # Universal classification helpers
    # ---------------------------------------------------------------------------

    def looks_like_section_heading(self, text: str) -> bool:
        """Return True if text is a generic section heading."""
        lower = _normalize(text)
        if lower in _SECTION_HEADING_PHRASES:
            return True
        return any(sub in lower for sub in _SECTION_HEADING_SUBSTRINGS)

    def looks_like_source_title(self, text: str, source_titles: list[str] | None = None) -> bool:
        """Return True if text matches a known source title or looks like an article title."""
        lower = _normalize(text)
        if source_titles:
            for title in source_titles:
                if _normalize(title) == lower:
                    return True
        # Heuristic: editorial patterns that indicate article/list titles
        editorial_patterns = (
            "best ",
            "top ",
            "vetted",
            "editor",
            "guide to",
            "list of",
            "ranked",
        )
        if any(lower.startswith(p) for p in editorial_patterns) and any(
            domain_kw in lower
            for domain_kw in ("perfume", "parfum", "fragrance", "makeup", "tools", "apps", "stocks")
            + (
                "watch",
                "watches",
                "luggage",
                "camera",
                "cameras",
                "headphones",
                "office chairs",
                "mattress",
                "laptops",
                "sneakers",
            )
        ):
            return True
        return False

    def looks_like_entity_cluster(self, text: str) -> bool:
        """Return True if text is a concatenation of multiple entity names."""
        brands = self.get_known_brands_or_entities()
        if not brands:
            return False
        # Count how many known entities appear in the string
        lower = text.lower()
        matched = sum(1 for brand in brands if brand.lower() in lower)
        return matched >= 3

    def looks_like_compound_candidate(self, text: str) -> bool:
        """Return True for explicit ``A or B``/``A and B`` recommendation names."""
        return bool(re.search(r"\s+(?:or|and)\s+", text, re.IGNORECASE))

    def looks_like_catalog_nav(self, text: str) -> bool:
        """Return True if text looks like navigation/catalog copy."""
        lower = _normalize(text)
        nav_phrases = (
            "shop now",
            "view all",
            "see all",
            "browse",
            "explore",
            "click here",
            "learn more",
            "read more",
            "find out",
        )
        return any(lower.startswith(p) for p in nav_phrases)

    def looks_like_url_or_citation(self, text: str) -> bool:
        """Return True if text is a URL or citation artifact."""
        lower = text.lower()
        for pat in _SOURCE_ARTIFACT_PATTERNS:
            if pat in lower:
                return True
        if _CITATION_PATTERNS.match(lower.strip()):
            return True
        return False

    # ---------------------------------------------------------------------------
    # Entity validation — override in domain subclasses
    # ---------------------------------------------------------------------------

    def is_valid_entity(self, name: str, query_contract: "QueryContract") -> bool:
        """Return True if name is a valid entity for this domain and contract.

        Base implementation: valid if not universally rejected.
        """
        if not name or len(name.strip()) < 2:
            return False
        if self.looks_like_section_heading(name):
            return False
        if self.looks_like_url_or_citation(name):
            return False
        if self.looks_like_catalog_nav(name):
            return False
        if self.looks_like_entity_cluster(name):
            return False
        if self.looks_like_compound_candidate(name):
            return False
        return True

    def get_rejection_reason(self, name: str, query_contract: "QueryContract") -> str | None:
        """Return a rejection reason string, or None if the entity is valid."""
        if not name or len(name.strip()) < 2:
            return "empty or too short"
        if self.looks_like_section_heading(name):
            return "section headings do not count"
        if self.looks_like_url_or_citation(name):
            return "URL/domain/citation artifact"
        if self.looks_like_catalog_nav(name):
            return "catalog navigation text"
        if self.looks_like_entity_cluster(name):
            return "entity cluster — multiple brands in one string"
        if self.looks_like_compound_candidate(name):
            return "compound candidate must be split into specific entities"
        return None

    def classify_entity_type(self, name: str, query_contract: "QueryContract") -> str:
        """Classify the entity type. Override for domain-specific types."""
        if self.looks_like_section_heading(name):
            return "section_heading"
        if self.looks_like_url_or_citation(name):
            return "unknown"
        if self.looks_like_entity_cluster(name):
            return "brand_cluster"
        if self.looks_like_compound_candidate(name):
            return "brand_cluster"
        return "unknown"

    def canonicalize(self, name: str) -> str:
        """Return a canonical/normalized form for deduplication."""
        return _normalize(name)

    # ---------------------------------------------------------------------------
    # Domain knowledge hooks — override in subclasses
    # ---------------------------------------------------------------------------

    def get_rejection_rules(self, query_contract: "QueryContract") -> list[str]:
        """Return list of rejection rule descriptions for this domain/contract."""
        return [
            "section headings do not count",
            "source titles do not count",
            "URL/domain/citation artifacts do not count",
            "catalog navigation text does not count",
            "entity clusters (multiple brands in one string) do not count",
        ]

    def get_product_indicators(self) -> list[str]:
        """Return domain-specific product signal terms."""
        return []

    def get_known_brands_or_entities(self) -> list[str]:
        """Return known brands or entity names for this domain."""
        return []

    def get_known_recommendation_entities(
        self, query_contract: "QueryContract"
    ) -> list[str]:
        """Return a small curated fallback universe of valid recommendation entities."""
        return []


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _normalize(text: str) -> str:
    """Normalize text for comparison."""
    text = text.strip().lower()
    text = re.sub(r"[*_`]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text
