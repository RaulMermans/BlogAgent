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
        "exxonmobil",
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
        # Energy sector companies commonly appearing in watchlists
        "brookfield renewable",
        "brookfield renewable partners",
        "american electric power",
        "american electric power company",
        "baker hughes",
        "baker hughes co",
        "bloom energy",
        "bloom energy corp",
        "nextera energy",
        "nextera",
        "enphase energy",
        "enphase",
        "first solar",
        "kinder morgan",
        "williams companies",
        "williams companies inc",
        "shell",
        "bp",
        "conocophillips",
        "schlumberger",
        "halliburton",
        "dominion energy",
        "duke energy",
        "southern company",
        "xcel energy",
        "sempra energy",
        "consolidated edison",
        "eversource energy",
        "atmos energy",
        "national fuel gas",
        "oge energy",
        "dte energy",
        "nrg energy",
        "vistra",
        "talen energy",
        "sunrun",
        "sunnova energy",
        "sunpower",
        "array technologies",
        "shoals technologies",
        "solaredge technologies",
        "solaredge",
        "plug power",
        "fuel cell energy",
        "ballard power systems",
        "clean energy fuels",
        "green plains",
        "renewable energy group",
        "brookfield asset management",
        "terraform power",
        "pattern energy",
        "innergex renewable energy",
        "boralex",
        "transalta renewables",
    }
)

# Generic finance category phrases that are NOT company/security names
_GENERIC_FINANCE_CATEGORIES: frozenset[str] = frozenset(
    {
        "energy stocks",
        "energy stock",
        "renewable energy stocks",
        "green energy stocks",
        "clean energy stocks",
        "top energy companies",
        "best energy companies",
        "energy sector",
        "energy market",
        "renewable energy leaders",
        "energy leaders",
        "green energy leaders",
        "investment tips",
        "stock tips",
        "buy tips",
        "investing tips",
        "watchlist picks",
        "top stocks",
        "best stocks",
        "growth stocks",
        "value stocks",
        "dividend stocks",
        "small cap stocks",
        "large cap stocks",
        "penny stocks",
        "hot stocks",
        "trending stocks",
        "opportunities",
        "investment opportunities",
        "energy opportunities",
    }
)

# Editorial heading substrings specific to finance articles
_FINANCE_HEADING_SUBSTRINGS: tuple[str, ...] = (
    "the shifting sands",
    "our approach to",
    "spotlight on key",
    "navigating the",
    "opportunities in 20",
    "key energy",
    "key players",
    "identifying energy",
    "identifying opportunities",
    "energy landscape",
    "energy market",
    "energy sector",
    "investment landscape",
    "for 2025",
    "for 2026",
    "for 2027",
    "sands of energy",
    "approach to identifying",
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

    # Company name signal words — indicate this is a company name vs. category phrase
    _COMPANY_SIGNALS: tuple[str, ...] = (
        "corp",
        "inc",
        "llc",
        "ltd",
        "co.",
        "plc",
        "group",
        "holdings",
        "partners",
        "capital",
        "fund",
        "trust",
        "bank",
        "energy",
        "power",
        "solar",
        "wind",
        "electric",
        "petroleum",
        "oil",
        "gas",
        "mining",
        "technologies",
        "tech",
        "systems",
        "solutions",
        "services",
        "financial",
        "investment",
        "asset",
        "management",
        "resources",
        "industries",
        "enterprises",
        "international",
        "global",
    )

    def is_valid_entity(self, name: str, query_contract: "QueryContract") -> bool:
        if not super().is_valid_entity(name, query_contract):
            return False

        lower = _normalize(name)

        if self._has_buy_sell_language(lower):
            return False

        # Reject generic category phrases
        if lower in _GENERIC_FINANCE_CATEGORIES:
            return False

        # Reject domain-specific editorial headings
        if self._is_finance_heading(lower):
            return False

        # Accept known companies/ETFs
        if lower in _KNOWN_FINANCIAL_ENTITIES:
            return True

        # Accept ticker-like patterns (1-5 uppercase letters)
        if _TICKER_PATTERN.match(name.strip()):
            return True

        return self._looks_like_company_or_security(name, lower)

    def get_rejection_reason(self, name: str, query_contract: "QueryContract") -> str | None:
        base_reason = super().get_rejection_reason(name, query_contract)
        if base_reason:
            return base_reason

        lower = _normalize(name)
        if self._has_buy_sell_language(lower):
            return "direct buy/sell language violates safety constraints"

        if lower in _GENERIC_FINANCE_CATEGORIES:
            return "generic finance category phrases do not count — need a company/security name"

        if self._is_finance_heading(lower):
            return "section headings do not count as company/security recommendations"

        if not self.is_valid_entity(name, query_contract):
            return "not a recognized public company, ticker, or security"

        return None

    def classify_entity_type(self, name: str, query_contract: "QueryContract") -> str:
        base_type = super().classify_entity_type(name, query_contract)
        if base_type not in ("unknown",):
            return base_type

        lower = _normalize(name)
        if lower in _GENERIC_FINANCE_CATEGORIES:
            return "category"
        if self._is_finance_heading(lower):
            return "section_heading"
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
                "generic category phrases like 'energy stocks' do not count",
                "section headings do not count as company/security names",
            ]
        )
        return rules

    def get_known_brands_or_entities(self) -> list[str]:
        return sorted(_KNOWN_FINANCIAL_ENTITIES)

    def _is_finance_heading(self, lower: str) -> bool:
        """Return True if the text is an editorial heading, not a company name."""
        return any(sub in lower for sub in _FINANCE_HEADING_SUBSTRINGS)

    def _looks_like_company_or_security(self, original_name: str, lower: str) -> bool:
        """Return True if the name looks like a company or security name.

        Requires:
        - 1-5 words
        - No year patterns (article headings often contain years)
        - No generic category words
        - Has a company signal word OR first word is capitalized proper noun
        """
        words = lower.split()
        if not (1 <= len(words) <= 5):
            return False

        # Reject if contains year patterns (article headings often have years)
        if re.search(r"\b20\d\d\b", lower):
            return False

        # Reject generic non-company words
        _GENERIC_NOUNS = frozenset(
            {
                "opportunities",
                "approach",
                "landscape",
                "sands",
                "shifting",
                "stocks",
                "investing",
                "players",
                "spotlight",
                "navigating",
                "overview",
                "analysis",
                "summary",
                "guide",
                "tips",
                "strategies",
                "methods",
                "ways",
                "factors",
                "risks",
                "rewards",
                "returns",
                "growth",
                "trends",
            }
        )
        if any(w in _GENERIC_NOUNS for w in words):
            return False

        # Has a company signal word
        if any(signal in lower for signal in self._COMPANY_SIGNALS):
            # Check that original name has some capitalization
            original_words = original_name.strip().split()
            if any(w and w[0].isupper() for w in original_words):
                return True

        # Short names (1-2 words) that are capitalized proper nouns
        original_words = original_name.strip().split()
        if 1 <= len(original_words) <= 2:
            if all(w and w[0].isupper() for w in original_words if w):
                # Not a generic single word
                _GENERIC_CAPS = frozenset(
                    {
                        "The",
                        "A",
                        "An",
                        "In",
                        "Of",
                        "For",
                        "And",
                        "Or",
                        "But",
                        "Top",
                        "Best",
                        "New",
                        "Good",
                        "Great",
                        "Free",
                        "All",
                        "Energy",
                        "Stocks",
                        "Companies",
                        "Market",
                        "Sector",
                    }
                )
                if not any(w in _GENERIC_CAPS for w in original_words):
                    return True

        return False

    def _has_buy_sell_language(self, lower: str) -> bool:
        return any(phrase in lower for phrase in _BUY_SELL_PHRASES)
