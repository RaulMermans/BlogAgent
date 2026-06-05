"""Consumer products domain adapter.

Valid: named product models and product lines for generic product recommendations.
Invalid: generic category phrases, buying-guide headings, sale/navigation copy,
and brand-only names when the contract requires specific products.

Permission class: read_only
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from blogagent.tools.domain_adapters.base import DomainAdapter, _normalize

if TYPE_CHECKING:
    from blogagent.workflow.query_contract import QueryContract

_KNOWN_PRODUCT_NAMES: frozenset[str] = frozenset(
    {
        "tissot prx quartz",
        "seiko 5 sports",
        "hamilton khaki field mechanical",
        "orient bambino",
        "citizen tsuyosa",
        "longines conquest",
        "sony wh-1000xm5",
        "bose quietcomfort ultra",
        "apple airpods pro",
        "samsonite freeform",
        "away bigger carry-on",
        "away bigger carry on",
        "travelpro platinum elite",
        "fujifilm x-t30 ii",
        "canon eos r50",
        "herman miller aeron",
        "steelcase series 1",
    }
)

_KNOWN_BRANDS: frozenset[str] = frozenset(
    {
        "tissot",
        "seiko",
        "hamilton",
        "orient",
        "citizen",
        "longines",
        "sony",
        "bose",
        "apple",
        "samsonite",
        "away",
        "travelpro",
        "fujifilm",
        "canon",
        "nikon",
        "panasonic",
        "olympus",
        "leica",
        "herman miller",
        "steelcase",
        "secretlab",
        "hon",
        "branch",
        "anker",
        "jbl",
        "sennheiser",
        "audio-technica",
        "dell",
        "hp",
        "lenovo",
        "asus",
        "acer",
        "microsoft",
        "breville",
        "delonghi",
        "kitchenaid",
        "dyson",
        "shark",
        "casper",
        "purple",
        "tempur-pedic",
        "nike",
        "adidas",
        "new balance",
        "allbirds",
        "common projects",
    }
)

_GENERIC_PRODUCT_PHRASES: frozenset[str] = frozenset(
    {
        "affordable luxury watches",
        "best luxury watches",
        "luxury watches",
        "watch brands",
        "luxury brands",
        "men's watches",
        "mens watches",
        "women's watches",
        "womens watches",
        "buying guide",
        "top picks",
        "our picks",
        "best picks",
        "final takeaway",
        "how we chose",
        "how we tested",
        "what makes a great watch",
        "discerning tastes",
        "under $500",
        "under 500",
        "shop now",
        "on sale",
    }
)

_CATEGORY_WORDS: frozenset[str] = frozenset(
    {
        "watches",
        "watch",
        "luggage",
        "backpacks",
        "backpack",
        "cameras",
        "camera",
        "headphones",
        "headphone",
        "office chairs",
        "office chair",
        "sneakers",
        "mattresses",
        "coffee machines",
        "kitchen gear",
        "travel gear",
        "home products",
    }
)

_MODEL_TOKEN_RE = re.compile(r"^(?=.*[a-zA-Z])(?=.*\d)[A-Za-z0-9][A-Za-z0-9+._/-]*$")
_PRICE_OR_SALE_RE = re.compile(
    r"(?:\s*[-–—:|]\s*)?(?:now\s+)?(?:on\s+sale|sale|deal|shop now|from)?\s*"
    r"(?:\$|usd\s*)\d+(?:[,.]\d{2})?.*$",
    re.IGNORECASE,
)


class GenericProductAdapter(DomainAdapter):
    """Domain adapter for generic consumer product recommendation lists."""

    domain: str = "consumer_products"

    def is_valid_entity(self, name: str, query_contract: "QueryContract") -> bool:
        if not super().is_valid_entity(name, query_contract):
            return False

        canonical = self.canonicalize(name)
        lower = _normalize(canonical)

        if not lower or lower in _GENERIC_PRODUCT_PHRASES:
            return False
        if self._is_sale_or_nav(lower):
            return False
        if self._is_generic_product_category(lower, query_contract):
            return query_contract.answer_entity_type == "product_category"
        if self._is_brand_only(lower):
            return False
        if lower in _KNOWN_PRODUCT_NAMES:
            return True
        if self._has_brand_and_model(lower):
            return True
        if self._looks_like_capitalized_product_model(canonical):
            return True
        return False

    def get_rejection_reason(self, name: str, query_contract: "QueryContract") -> str | None:
        base_reason = super().get_rejection_reason(name, query_contract)
        if base_reason:
            return base_reason

        canonical = self.canonicalize(name)
        lower = _normalize(canonical)
        if lower in _GENERIC_PRODUCT_PHRASES:
            return "generic product/category phrase does not count"
        if self._is_sale_or_nav(lower):
            return "sale/shop/navigation text does not count"
        if self._is_generic_product_category(lower, query_contract):
            if query_contract.answer_entity_type == "product_category":
                return None
            return "generic product categories do not count when specific products are required"
        if self._is_brand_only(lower):
            return "brand-only names do not count as specific product recommendations"
        if not self.is_valid_entity(name, query_contract):
            return "not a named product model or product line"
        return None

    def classify_entity_type(self, name: str, query_contract: "QueryContract") -> str:
        base_type = super().classify_entity_type(name, query_contract)
        if base_type not in ("unknown",):
            return base_type

        lower = _normalize(self.canonicalize(name))
        if self._is_brand_only(lower):
            return "brand"
        if self._is_generic_product_category(lower, query_contract):
            return "category"
        if self.is_valid_entity(name, query_contract):
            return "specific_product"
        return "unknown"

    def canonicalize(self, name: str) -> str:
        cleaned = name.strip()
        cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
        cleaned = re.sub(r"[*_`]", "", cleaned)
        cleaned = _PRICE_OR_SALE_RE.sub("", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,;:!?\"'`-–—[](){}")
        return cleaned

    def get_rejection_rules(self, query_contract: "QueryContract") -> list[str]:
        return super().get_rejection_rules(query_contract) + [
            "brand-only names do not count when specific products are required",
            "generic product categories do not count unless the prompt asks for categories/types",
            "price, sale, shop, and navigation artifacts do not count",
        ]

    def get_product_indicators(self) -> list[str]:
        return sorted(_CATEGORY_WORDS)

    def get_known_brands_or_entities(self) -> list[str]:
        return sorted(_KNOWN_BRANDS | _KNOWN_PRODUCT_NAMES)

    def _is_sale_or_nav(self, lower: str) -> bool:
        return any(
            phrase in lower
            for phrase in ("shop now", "on sale", "buy now", "add to cart", "view deal")
        )

    def _is_brand_only(self, lower: str) -> bool:
        return lower in _KNOWN_BRANDS

    def _is_generic_product_category(
        self, lower: str, query_contract: "QueryContract"
    ) -> bool:
        if lower in _CATEGORY_WORDS:
            return True
        subtype = (query_contract.entity_subtype or "").replace("_", " ")
        if subtype and lower in {subtype, f"{subtype}s"}:
            return True
        if lower.startswith(("best ", "top ", "affordable ", "budget ", "luxury ")):
            return any(word in lower for word in _CATEGORY_WORDS)
        if lower.startswith(("under $", "under ")) and any(
            word in lower for word in _CATEGORY_WORDS
        ):
            return True
        return False

    def _has_brand_and_model(self, lower: str) -> bool:
        words = lower.split()
        if len(words) < 2 or len(words) > 8:
            return False
        for brand in _KNOWN_BRANDS:
            if lower.startswith(brand + " "):
                remainder = lower[len(brand) :].strip()
                if not remainder or remainder in _CATEGORY_WORDS:
                    return False
                return True
        return False

    def _looks_like_capitalized_product_model(self, name: str) -> bool:
        words = name.split()
        if len(words) < 2 or len(words) > 6:
            return False
        first = words[0].strip(".,;:")
        if not first or not first[0].isupper():
            return False
        if first.lower() in {"best", "top", "affordable", "budget", "luxury", "under"}:
            return False
        has_model_token = any(_MODEL_TOKEN_RE.match(w.strip(".,;:()")) for w in words[1:])
        has_capitalized_second = len(words) >= 2 and words[1][0].isupper()
        return has_model_token or has_capitalized_second
