"""Beauty/Fragrance domain adapter.

Valid entities: specific perfume/fragrance/cologne products.
Invalid entities: brand-only names, brand clusters, source titles, section headings.

Permission class: read_only
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from blogagent.tools.domain_adapters.base import DomainAdapter, _normalize

if TYPE_CHECKING:
    from blogagent.workflow.query_contract import QueryContract

# Known brand-only names (not valid as product recs unless prompt asks for brands)
_BRAND_ONLY_NAMES: frozenset[str] = frozenset(
    {
        "kilian",
        "by kilian",
        "glossier",
        "sol de janeiro",
        "tom ford",
        "chanel",
        "dior",
        "gucci",
        "guerlain",
        "byredo",
        "jo malone",
        "jo malone london",
        "armani",
        "giorgio armani",
        "ysl",
        "yves saint laurent",
        "maison francis kurkdjian",
        "dolce & gabbana",
        "ouai",
        "prada",
        "versace",
        "maison margiela",
        "hermes",
        "hermès",
        "valentino",
        "mugler",
        "burberry",
        "givenchy",
        "marc jacobs",
        "lancome",
        "lancôme",
        "calvin klein",
        "ralph lauren",
        "hugo boss",
        "viktor & rolf",
        "le labo",
        "diptyque",
        "creed",
        "amouage",
        "bvlgari",
        "bulgari",
        "bottega veneta",
    }
)

# Product signal terms — indicate this is a product name, not brand-only
_PRODUCT_SIGNAL_TERMS: frozenset[str] = frozenset(
    {
        "eau",
        "parfum",
        "perfume",
        "cologne",
        "fragrance",
        "toilette",
        "edp",
        "edt",
        "absolute",
        "absolu",
        "intense",
        "elixir",
        "no.",
        "no",
        "light blue",
        "soleil",
        "blanc",
        "terracotta",
        "aqua",
        "universalis",
        "melrose",
        "ocean",
        "gioia",
        "wood sage",
        "sea salt",
        "chance",
        "libre",
        "bloom",
        "sauvage",
        "replica",
        "afternoon",
        "delight",
        "flowerbomb",
        "black orchid",
        "oud",
        "neroli",
        "portofino",
        "soleil",
        "daisy",
    }
)

# Source title patterns specific to fragrance articles
_FRAGRANCE_SOURCE_TITLE_PATTERNS = (
    "best summer perfumes",
    "best summer fragrances",
    "best summer parfums",
    "best summer scents",
    "top summer fragrances",
    "editor-vetted",
    "best options",
    "fragrance wardrobe",
    "scent categories",
    "signature scent",
)

_FRAGRANCE_CATEGORY_PHRASES: frozenset[str] = frozenset(
    {
        "summer parfums",
        "summer perfumes",
        "summer fragrances",
        "summer scents",
        "signature scent",
        "fragrance wardrobe",
        "scent categories",
        "fragrance notes",
        "fresh scents",
        "floral scents",
        "woody scents",
    }
)

_CATALOG_ARTIFACT_TERMS: tuple[str, ...] = (
    "best seller",
    "best sellers",
    "bestseller",
    "bestsellers",
    "new arrivals",
    "shop all",
    "view all",
)

# Known brand prefixes used for brand-prefix extraction
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
    "kilian",
    "by kilian",
    "glossier",
    "sol de janeiro",
    "guerlain",
    "maison francis kurkdjian",
    "giorgio armani",
    "ouai",
    "viktor & rolf",
    "creed",
)


class BeautyFragranceAdapter(DomainAdapter):
    """Domain adapter for beauty/fragrance products."""

    domain: str = "beauty_fragrance"

    def is_valid_entity(self, name: str, query_contract: "QueryContract") -> bool:
        if not super().is_valid_entity(name, query_contract):
            return False

        lower = _normalize(name)
        asks_for_brands = query_contract.answer_entity_type == "fragrance_brand"

        if lower in _BRAND_ONLY_NAMES:
            return asks_for_brands

        if self._is_source_title_phrase(lower):
            return False

        if self._is_category_phrase(lower):
            return False

        if self._has_catalog_artifact(lower):
            return False

        return self._looks_like_specific_fragrance_product(lower)

    def get_rejection_reason(self, name: str, query_contract: "QueryContract") -> str | None:
        base_reason = super().get_rejection_reason(name, query_contract)
        if base_reason:
            return base_reason

        lower = _normalize(name)
        asks_for_brands = query_contract.answer_entity_type == "fragrance_brand"

        if lower in _BRAND_ONLY_NAMES:
            if asks_for_brands:
                return None
            return "brand-only names do not count as product recommendations"

        if self._is_source_title_phrase(lower):
            return "source titles do not count"

        if self._is_category_phrase(lower):
            return "category phrases do not count"

        if self._has_catalog_artifact(lower):
            return "catalog/navigation text does not count"

        if not self._looks_like_specific_fragrance_product(lower):
            return "not a specific fragrance product"

        return None

    def classify_entity_type(self, name: str, query_contract: "QueryContract") -> str:
        base_type = super().classify_entity_type(name, query_contract)
        if base_type not in ("unknown",):
            return base_type

        lower = _normalize(name)
        if lower in _BRAND_ONLY_NAMES:
            return "brand"
        if self._is_source_title_phrase(lower):
            return "source_title"
        if self._is_category_phrase(lower):
            return "category"
        if self._has_catalog_artifact(lower):
            return "source_nav"
        if self._looks_like_specific_fragrance_product(lower):
            return "specific_product"
        return "unknown"

    def get_rejection_rules(self, query_contract: "QueryContract") -> list[str]:
        rules = super().get_rejection_rules(query_contract)
        rules.extend(
            [
                "brand-only names do not count as product recommendations",
                "source title phrases do not count",
                "fragrance category phrases (e.g. 'summer parfums') do not count",
                "brand clusters (multiple brand names in one string) do not count",
            ]
        )
        return rules

    def get_product_indicators(self) -> list[str]:
        return sorted(_PRODUCT_SIGNAL_TERMS)

    def get_known_brands_or_entities(self) -> list[str]:
        return list(_BRAND_PREFIXES)

    # ---------------------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------------------

    def _is_source_title_phrase(self, lower: str) -> bool:
        return any(pat in lower for pat in _FRAGRANCE_SOURCE_TITLE_PATTERNS)

    def _is_category_phrase(self, lower: str) -> bool:
        if lower in _FRAGRANCE_CATEGORY_PHRASES:
            return True
        if lower.startswith(("best options", "best perfumes", "best parfums", "best fragrances")):
            return True
        if len(lower.split()) <= 4 and any(
            lower.endswith(t) for t in ("perfumes", "parfums", "fragrances", "scents", "colognes")
        ):
            return True
        return False

    def _has_catalog_artifact(self, lower: str) -> bool:
        return any(term in lower for term in _CATALOG_ARTIFACT_TERMS)

    def _looks_like_specific_fragrance_product(self, lower: str) -> bool:
        words = lower.split()
        if len(words) < 2 or len(words) > 8:
            return False
        if lower in _BRAND_ONLY_NAMES:
            return False
        if any(signal in lower for signal in _PRODUCT_SIGNAL_TERMS):
            return True
        for brand in _BRAND_ONLY_NAMES:
            if lower.startswith(brand + " ") and len(words) > len(brand.split()):
                return True
        return False
