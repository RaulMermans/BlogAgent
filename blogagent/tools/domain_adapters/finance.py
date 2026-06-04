"""Finance domain adapter.

Valid: public companies, tickers, sector ETFs (with safety framing).
Invalid: direct buy/sell advice, unsupported tickers, crypto-promotional content.

Safety constraints are enforced at the contract level.
Permission class: read_only
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from blogagent.tools.domain_adapters.base import DomainAdapter, _normalize

if TYPE_CHECKING:
    from blogagent.workflow.query_contract import QueryContract

# Ticker-like patterns
_TICKER_PATTERN = re.compile(r"^[A-Z]{1,5}(-[A-Z]{1,3})?$")

# Known large-cap companies / ETFs
_KNOWN_FINANCIAL_ENTITIES: frozenset[str] = frozenset(
    {
        "apple",
        "microsoft",
        "alphabet",
        "google",
        "amazon",
        "meta",
        "nvidia",
        "tesla",
        "berkshire hathaway",
        "exxon mobil",
        "chevron",
        "jpmorgan",
        "jpmorgan chase",
        "bank of america",
        "wells fargo",
        "goldman sachs",
        "morgan stanley",
        "johnson & johnson",
        "unitedhealth",
        "procter & gamble",
        "spdr",
        "vanguard",
        "ishares",
        "invesco",
        "xle",
        "xlf",
        "qqq",
        "spy",
        "voo",
        "aapl",
        "msft",
        "googl",
        "amzn",
        "meta",
        "nvda",
        "tsla",
        "brk.b",
        "xom",
        "cvx",
        "jpm",
        "bac",
        "wfc",
        "gs",
        "ms",
        "jnj",
        "unh",
        "pg",
    }
)

# Phrases that signal direct buy/sell advice (should be rejected)
_BUY_SELL_PHRASES: tuple[str, ...] = (
    "buy now",
    "buy this",
    "buy these",
    "guaranteed return",
    "guaranteed profit",
    "will definitely",
    "sure to rise",
    "sure to increase",
    "no-brainer investment",
    "can't lose",
)


class FinanceAdapter(DomainAdapter):
    """Domain adapter for financial securities and companies."""

    domain: str = "finance"

    def is_valid_entity(self, name: str, query_contract: "QueryContract") -> bool:
        if not super().is_valid_entity(name, query_contract):
            return False

        lower = _normalize(name)

        if self._has_buy_sell_language(lower):
            return False

        if lower in _KNOWN_FINANCIAL_ENTITIES:
            return True

        if _TICKER_PATTERN.match(name.strip()):
            return True

        return self._looks_like_company_or_security(lower)

    def get_rejection_reason(self, name: str, query_contract: "QueryContract") -> str | None:
        base_reason = super().get_rejection_reason(name, query_contract)
        if base_reason:
            return base_reason

        lower = _normalize(name)
        if self._has_buy_sell_language(lower):
            return "direct buy/sell language violates safety constraints"

        if not self.is_valid_entity(name, query_contract):
            return "not a recognized public company, ticker, or security"

        return None

    def classify_entity_type(self, name: str, query_contract: "QueryContract") -> str:
        base_type = super().classify_entity_type(name, query_contract)
        if base_type not in ("unknown",):
            return base_type

        lower = _normalize(name)
        if lower in _KNOWN_FINANCIAL_ENTITIES:
            return "company"
        if _TICKER_PATTERN.match(name.strip()):
            return "security"
        return "unknown"

    def get_rejection_rules(self, query_contract: "QueryContract") -> list[str]:
        rules = super().get_rejection_rules(query_contract)
        rules.extend(
            [
                "direct buy/sell recommendations violate safety constraints",
                "unsupported price targets are not allowed",
                "financial disclaimer is required",
                "performance predictions must be attributed to a source",
            ]
        )
        return rules

    def get_known_brands_or_entities(self) -> list[str]:
        return sorted(_KNOWN_FINANCIAL_ENTITIES)

    def _looks_like_company_or_security(self, lower: str) -> bool:
        words = lower.split()
        # Company names typically have 1-5 words and start with a capital
        return 1 <= len(words) <= 5

    def _has_buy_sell_language(self, lower: str) -> bool:
        return any(phrase in lower for phrase in _BUY_SELL_PHRASES)
