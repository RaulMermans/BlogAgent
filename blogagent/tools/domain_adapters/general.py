"""General domain adapter — fallback for explainer and non-domain topics.

For explainer/how-to posts, the candidate ledger is not required.
This adapter applies only universal rejection rules.

Permission class: read_only
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from blogagent.tools.domain_adapters.base import DomainAdapter

if TYPE_CHECKING:
    from blogagent.workflow.query_contract import QueryContract


class GeneralAdapter(DomainAdapter):
    """General-purpose adapter for explainer and non-domain topics."""

    domain: str = "general"

    def is_valid_entity(self, name: str, query_contract: "QueryContract") -> bool:
        return super().is_valid_entity(name, query_contract)

    def get_rejection_rules(self, query_contract: "QueryContract") -> list[str]:
        return super().get_rejection_rules(query_contract)

    def get_product_indicators(self) -> list[str]:
        return []

    def get_known_brands_or_entities(self) -> list[str]:
        return []
