"""Domain adapter package for entity extraction and validation.

Each adapter handles domain-specific entity classification rules.
The base adapter provides universal rejection logic.
"""

from __future__ import annotations

from blogagent.tools.domain_adapters.base import DomainAdapter
from blogagent.tools.domain_adapters.beauty_fragrance import BeautyFragranceAdapter
from blogagent.tools.domain_adapters.beauty_makeup import BeautyMakeupAdapter
from blogagent.tools.domain_adapters.fashion_lifestyle import FashionLifestyleAdapter
from blogagent.tools.domain_adapters.finance import FinanceAdapter
from blogagent.tools.domain_adapters.general import GeneralAdapter
from blogagent.tools.domain_adapters.software_tools import SoftwareToolsAdapter

_ADAPTER_REGISTRY: dict[str, DomainAdapter] = {
    "beauty_fragrance": BeautyFragranceAdapter(),
    "beauty_makeup": BeautyMakeupAdapter(),
    "fashion_lifestyle": FashionLifestyleAdapter(),
    "software_tools": SoftwareToolsAdapter(),
    "finance": FinanceAdapter(),
    "general": GeneralAdapter(),
}


def get_adapter(domain: str) -> DomainAdapter:
    """Return the adapter for the given domain, falling back to general."""
    return _ADAPTER_REGISTRY.get(domain, _ADAPTER_REGISTRY["general"])


__all__ = [
    "DomainAdapter",
    "BeautyFragranceAdapter",
    "BeautyMakeupAdapter",
    "FashionLifestyleAdapter",
    "SoftwareToolsAdapter",
    "FinanceAdapter",
    "GeneralAdapter",
    "get_adapter",
]
