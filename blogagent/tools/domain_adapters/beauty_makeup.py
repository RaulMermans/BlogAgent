"""Beauty/Makeup domain adapter.

Valid: specific makeup products, product lines, product categories (when essentials asked).
Invalid: brand-only unless prompt asks for brands, section headings, source titles.

Permission class: read_only
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from blogagent.tools.domain_adapters.base import DomainAdapter, _normalize

if TYPE_CHECKING:
    from blogagent.workflow.query_contract import QueryContract

_MAKEUP_PRODUCT_INDICATORS: frozenset[str] = frozenset(
    {
        "foundation",
        "concealer",
        "blush",
        "bronzer",
        "highlighter",
        "mascara",
        "eyeliner",
        "eyeshadow",
        "lipstick",
        "lip gloss",
        "lip liner",
        "lip balm",
        "setting powder",
        "setting spray",
        "primer",
        "contour",
        "tinted moisturizer",
        "bb cream",
        "cc cream",
        "serum",
        "moisturizer",
        "toner",
        "spf",
        "sunscreen",
        "blush stick",
        "cream blush",
        "liquid blush",
        "palette",
        "eyebrow",
        "brow",
        "lash",
    }
)

_MAKEUP_BRAND_ONLY_NAMES: frozenset[str] = frozenset(
    {
        "nars",
        "mac",
        "charlotte tilbury",
        "rare beauty",
        "fenty beauty",
        "glossier",
        "too faced",
        "urban decay",
        "maybelline",
        "l'oreal",
        "loreal",
        "covergirl",
        "e.l.f.",
        "elf cosmetics",
        "morphe",
        "colourpop",
        "milani",
        "wet n wild",
        "revlon",
        "rimmel",
        "barry m",
        "huda beauty",
        "kylie cosmetics",
        "pat mcgrath",
        "bobbi brown",
        "laura mercier",
        "make up for ever",
        "dior beauty",
        "chanel beauty",
        "armani beauty",
    }
)


class BeautyMakeupAdapter(DomainAdapter):
    """Domain adapter for beauty/makeup products."""

    domain: str = "beauty_makeup"

    def is_valid_entity(self, name: str, query_contract: "QueryContract") -> bool:
        if not super().is_valid_entity(name, query_contract):
            return False

        lower = _normalize(name)
        allows_categories = (
            query_contract.answer_entity_type == "specific_product_or_product_category"
        )
        asks_for_brands = "brand" in query_contract.answer_entity_type.lower()

        if lower in _MAKEUP_BRAND_ONLY_NAMES:
            return asks_for_brands

        if any(indicator in lower for indicator in _MAKEUP_PRODUCT_INDICATORS):
            return True

        if allows_categories and self._is_makeup_category(lower):
            return True

        return self._looks_like_makeup_product(lower)

    def get_rejection_reason(self, name: str, query_contract: "QueryContract") -> str | None:
        base_reason = super().get_rejection_reason(name, query_contract)
        if base_reason:
            return base_reason

        lower = _normalize(name)
        asks_for_brands = "brand" in query_contract.answer_entity_type.lower()

        if lower in _MAKEUP_BRAND_ONLY_NAMES:
            if asks_for_brands:
                return None
            return "brand-only names do not count as product recommendations"

        if not self.is_valid_entity(name, query_contract):
            return "not a specific makeup product"

        return None

    def classify_entity_type(self, name: str, query_contract: "QueryContract") -> str:
        base_type = super().classify_entity_type(name, query_contract)
        if base_type not in ("unknown",):
            return base_type

        lower = _normalize(name)
        if lower in _MAKEUP_BRAND_ONLY_NAMES:
            return "brand"
        if any(indicator in lower for indicator in _MAKEUP_PRODUCT_INDICATORS):
            return "specific_product"
        if self._is_makeup_category(lower):
            return "product_category"
        return "unknown"

    def get_product_indicators(self) -> list[str]:
        return sorted(_MAKEUP_PRODUCT_INDICATORS)

    def get_known_brands_or_entities(self) -> list[str]:
        return sorted(_MAKEUP_BRAND_ONLY_NAMES)

    def _is_makeup_category(self, lower: str) -> bool:
        categories = (
            "mascara",
            "foundation",
            "blush",
            "concealer",
            "eyeshadow",
            "eyeliner",
            "lipstick",
            "primer",
            "setting spray",
            "highlighter",
            "bronzer",
            "brow",
        )
        return any(cat in lower for cat in categories) and len(lower.split()) <= 4

    def _looks_like_makeup_product(self, lower: str) -> bool:
        words = lower.split()
        if len(words) < 2 or len(words) > 8:
            return False
        for brand in _MAKEUP_BRAND_ONLY_NAMES:
            if lower.startswith(brand + " ") and len(words) > len(brand.split()):
                return True
        return False
