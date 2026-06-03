"""Fashion/Lifestyle domain adapter.

Valid: clothing items, accessories, actionable style categories.
Invalid: generic headings, vague 'summer style' phrases, source titles.

Permission class: read_only
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from blogagent.tools.domain_adapters.base import DomainAdapter, _normalize

if TYPE_CHECKING:
    from blogagent.workflow.query_contract import QueryContract

_FASHION_PRODUCT_INDICATORS: frozenset[str] = frozenset(
    {
        "shirt",
        "t-shirt",
        "tee",
        "blouse",
        "top",
        "sweater",
        "cardigan",
        "jacket",
        "blazer",
        "coat",
        "trench",
        "dress",
        "skirt",
        "pants",
        "trousers",
        "jeans",
        "shorts",
        "leggings",
        "jumpsuit",
        "romper",
        "suit",
        "sneakers",
        "boots",
        "sandals",
        "heels",
        "loafers",
        "bag",
        "handbag",
        "backpack",
        "tote",
        "crossbody",
        "belt",
        "scarf",
        "hat",
        "cap",
        "sunglasses",
        "watch",
        "necklace",
        "earrings",
        "bracelet",
        "ring",
        "linen",
        "cotton",
        "denim",
        "leather",
        "silk",
    }
)

_FASHION_BRAND_NAMES: frozenset[str] = frozenset(
    {
        "zara",
        "h&m",
        "asos",
        "uniqlo",
        "gap",
        "j.crew",
        "mango",
        "nordstrom",
        "madewell",
        "everlane",
        "eileen fisher",
        "banana republic",
        "brooks brothers",
        "ralph lauren",
        "tommy hilfiger",
        "calvin klein",
        "levi's",
        "levis",
    }
)


class FashionLifestyleAdapter(DomainAdapter):
    """Domain adapter for fashion/lifestyle items."""

    domain: str = "fashion_lifestyle"

    def is_valid_entity(self, name: str, query_contract: "QueryContract") -> bool:
        if not super().is_valid_entity(name, query_contract):
            return False

        lower = _normalize(name)
        if lower in _FASHION_BRAND_NAMES:
            return False

        if any(indicator in lower for indicator in _FASHION_PRODUCT_INDICATORS):
            return True

        return self._looks_like_fashion_item(lower)

    def get_rejection_reason(self, name: str, query_contract: "QueryContract") -> str | None:
        base_reason = super().get_rejection_reason(name, query_contract)
        if base_reason:
            return base_reason

        lower = _normalize(name)
        if lower in _FASHION_BRAND_NAMES:
            return "brand-only names do not count unless prompt asks for brands"

        if not self.is_valid_entity(name, query_contract):
            return "not a specific fashion item"

        return None

    def classify_entity_type(self, name: str, query_contract: "QueryContract") -> str:
        base_type = super().classify_entity_type(name, query_contract)
        if base_type not in ("unknown",):
            return base_type

        lower = _normalize(name)
        if lower in _FASHION_BRAND_NAMES:
            return "brand"
        if any(indicator in lower for indicator in _FASHION_PRODUCT_INDICATORS):
            return "specific_product"
        return "unknown"

    def get_product_indicators(self) -> list[str]:
        return sorted(_FASHION_PRODUCT_INDICATORS)

    def get_known_brands_or_entities(self) -> list[str]:
        return sorted(_FASHION_BRAND_NAMES)

    def _looks_like_fashion_item(self, lower: str) -> bool:
        words = lower.split()
        if len(words) < 1 or len(words) > 6:
            return False
        for brand in _FASHION_BRAND_NAMES:
            if lower.startswith(brand + " ") and len(words) > len(brand.split()):
                return True
        return False
