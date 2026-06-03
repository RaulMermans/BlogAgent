"""Query contract construction for BlogAgent.

The contract turns a broad intent ("recommendation") into an explicit answer
shape the rest of the pipeline can enforce deterministically.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

TaskType = Literal["recommendation", "explainer", "how_to", "comparison", "analysis", "unknown"]
Domain = Literal[
    "beauty_fragrance",
    "beauty_makeup",
    "fashion_lifestyle",
    "finance",
    "general",
]


class QueryContract(BaseModel):
    task_type: TaskType = "unknown"
    domain: Domain = "general"
    requested_count: Optional[int] = None
    answer_entity_type: str = "unknown"
    valid_item_rules: list[str] = Field(default_factory=list)
    invalid_item_rules: list[str] = Field(default_factory=list)
    required_evidence_fields: list[str] = Field(default_factory=list)
    minimum_publishable_items: int = 1
    evidence_limited_allowed: bool = False
    exact_count_required: bool = False


_FRAGRANCE_TERMS = (
    "perfume",
    "perfumes",
    "parfum",
    "parfums",
    "fragrance",
    "fragrances",
    "cologne",
    "scent",
    "eau de",
)
_MAKEUP_TERMS = ("makeup", "mascara", "foundation", "lipstick", "concealer", "blush")
_FASHION_TERMS = ("fashion", "outfit", "style", "shoes", "bags", "wardrobe")
_HOW_TO_TERMS = ("how to", "how do", "steps to", "guide to")
_COMPARISON_TERMS = (" vs ", " versus ", "compare", "comparison")
_ANALYSIS_TERMS = ("analysis", "what caused", "trend", "forecast")
_BRAND_QUERY_TERMS = ("brands", "houses", "labels")


def build_query_contract(
    topic: str,
    *,
    is_recommendation: bool,
    is_financial: bool,
    requested_count: Optional[int],
) -> QueryContract:
    """Build the deterministic answer contract for a topic."""
    lower = topic.lower()
    task_type: TaskType
    if is_recommendation:
        task_type = "recommendation"
    elif any(t in lower for t in _HOW_TO_TERMS):
        task_type = "how_to"
    elif any(t in lower for t in _COMPARISON_TERMS):
        task_type = "comparison"
    elif any(t in lower for t in _ANALYSIS_TERMS):
        task_type = "analysis"
    elif lower.strip():
        task_type = "explainer"
    else:
        task_type = "unknown"

    if is_financial or any(t in lower for t in ("stock", "stocks", "invest", "crypto", "etf")):
        domain: Domain = "finance"
    elif any(t in lower for t in _FRAGRANCE_TERMS):
        domain = "beauty_fragrance"
    elif any(t in lower for t in _MAKEUP_TERMS):
        domain = "beauty_makeup"
    elif any(t in lower for t in _FASHION_TERMS):
        domain = "fashion_lifestyle"
    else:
        domain = "general"

    if domain == "beauty_fragrance" and task_type == "recommendation":
        asks_for_brands = any(t in lower for t in _BRAND_QUERY_TERMS)
        return QueryContract(
            task_type=task_type,
            domain=domain,
            requested_count=requested_count,
            answer_entity_type=(
                "fragrance_brand" if asks_for_brands else "specific_fragrance_product"
            ),
            valid_item_rules=[
                "must be a specific perfume/fragrance/parfum/cologne product",
                "must not be a brand-only name unless prompt explicitly asks for brands",
                "must have source evidence",
                "should include summer/date/festival/use-case rationale when applicable",
            ],
            invalid_item_rules=[
                "section headings do not count",
                "source titles do not count",
                "category phrases do not count",
                "brand-only names do not count as product recommendations",
                "SEO keywords do not count",
                "citations alone do not count",
            ],
            required_evidence_fields=[
                "name",
                "source_urls",
                "source_titles",
                "source_quality",
                "evidence_terms",
                "supported_context",
            ],
            minimum_publishable_items=3,
            evidence_limited_allowed=True,
            exact_count_required=requested_count is not None,
        )

    if domain == "finance" and task_type == "recommendation":
        return QueryContract(
            task_type=task_type,
            domain=domain,
            requested_count=requested_count,
            answer_entity_type="financial_security_watchlist",
            valid_item_rules=[
                "must be framed as educational watchlist material, not buy advice",
                "must include risk and uncertainty context",
                "must have source evidence",
            ],
            invalid_item_rules=[
                "do not use buy/guaranteed-return language",
                "do not present unsupported price targets",
                "do not omit financial disclaimer",
            ],
            required_evidence_fields=["name", "source_urls", "source_quality", "risk_context"],
            minimum_publishable_items=3,
            evidence_limited_allowed=True,
            exact_count_required=requested_count is not None,
        )

    return QueryContract(
        task_type=task_type,
        domain=domain,
        requested_count=requested_count,
        answer_entity_type="general_answer",
        valid_item_rules=["answer must be supported by source evidence"],
        invalid_item_rules=["unsupported high-importance claims do not count"],
        required_evidence_fields=["fact", "source_url", "confidence"],
        minimum_publishable_items=1,
        evidence_limited_allowed=False,
        exact_count_required=False,
    )
