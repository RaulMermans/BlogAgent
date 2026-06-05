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
    "software_tools",
    "finance",
    "consumer_products",
    "general",
]


class QueryContract(BaseModel):
    task_type: TaskType = "unknown"
    domain: Domain = "general"
    requested_count: Optional[int] = None
    answer_entity_type: str = "unknown"
    entity_subtype: Optional[str] = None
    valid_item_rules: list[str] = Field(default_factory=list)
    invalid_item_rules: list[str] = Field(default_factory=list)
    required_evidence_fields: list[str] = Field(default_factory=list)
    minimum_publishable_items: int = 1
    evidence_limited_allowed: bool = False
    exact_count_required: bool = False
    safety_constraints: list[str] = Field(default_factory=list)


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
_MAKEUP_TERMS = ("makeup", "mascara", "foundation", "lipstick", "concealer", "blush", "eyeshadow")
_FASHION_TERMS = (
    "fashion",
    "outfit",
    "style",
    "shoes",
    "sneaker",
    "sneakers",
    "bags",
    "wardrobe",
    "capsule",
    "clothes",
)
_SOFTWARE_TERMS = ("tools", "apps", "software", "platform", "plugin", "extension", "ai tools")
_HOW_TO_TERMS = ("how to", "how do", "steps to", "guide to")
_COMPARISON_TERMS = (" vs ", " versus ", "compare", "comparison")
_ANALYSIS_TERMS = ("analysis", "what caused", "trend", "forecast")
_BRAND_QUERY_TERMS = ("brands", "houses", "labels")
_RECOMMENDATION_INTENT_TERMS = ("best", "top", "recommend", "recommendation", "picks")
_CATEGORY_QUERY_TERMS = ("categories", "category", "essentials", "types", "kinds")

_CONSUMER_PRODUCT_SUBTYPES: dict[str, tuple[str, ...]] = {
    "watch": ("watch", "watches"),
    "luggage": ("luggage", "carry-on", "carry on", "suitcase", "suitcases"),
    "backpack": ("backpack", "backpacks"),
    "camera": ("camera", "cameras"),
    "headphone": ("headphone", "headphones", "earbuds", "earbud"),
    "office_chair": ("office chair", "office chairs", "desk chair", "desk chairs"),
    "mattress": ("mattress", "mattresses"),
    "coffee_machine": ("coffee machine", "coffee machines", "espresso machine", "coffee maker"),
    "laptop": ("laptop", "laptops"),
    "skincare_product": ("skincare", "skin care", "serum", "sunscreen", "moisturizer"),
    "kitchen_gear": ("kitchen gear", "cookware", "knife", "knives", "air fryer", "blender"),
    "travel_gear": ("travel gear", "packing cube", "travel pillow"),
    "home_product": ("home product", "home products", "vacuum", "robot vacuum", "air purifier"),
}


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
    elif any(t in lower for t in _SOFTWARE_TERMS):
        domain = "software_tools"
    elif task_type == "recommendation" and _contains_consumer_product_phrase(lower):
        domain = "consumer_products"
    elif (
        task_type == "recommendation"
        and requested_count is not None
        and any(t in lower for t in _RECOMMENDATION_INTENT_TERMS)
    ):
        domain = "consumer_products"
    else:
        domain = "general"

    if domain == "beauty_fragrance" and task_type == "recommendation":
        asks_for_brands = any(t in lower for t in _BRAND_QUERY_TERMS)
        return QueryContract(
            task_type=task_type,
            domain=domain,
            requested_count=requested_count,
            answer_entity_type="fragrance_brand" if asks_for_brands else "specific_product",
            entity_subtype=None if asks_for_brands else "fragrance_product",
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
                "brand clusters (multiple brand names in one string) do not count",
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

    if domain == "beauty_makeup" and task_type == "recommendation":
        asks_for_essentials = any(
            t in lower for t in ("essentials", "basics", "kit", "routine", "bag")
        )
        return QueryContract(
            task_type=task_type,
            domain=domain,
            requested_count=requested_count,
            answer_entity_type=(
                "specific_product_or_product_category"
                if asks_for_essentials
                else "specific_product"
            ),
            entity_subtype="makeup_product",
            valid_item_rules=[
                "must be a specific makeup product or named product line",
                "product category allowed if prompt asks for essentials/basics/kit",
                "must have source evidence",
            ],
            invalid_item_rules=[
                "brand-only names do not count unless prompt asks for brands",
                "section headings do not count",
                "source titles do not count",
                "vague generic terms like 'festival makeup' do not count",
            ],
            required_evidence_fields=["name", "source_urls", "source_quality", "evidence_terms"],
            minimum_publishable_items=3,
            evidence_limited_allowed=True,
            exact_count_required=requested_count is not None,
        )

    if domain == "fashion_lifestyle" and task_type == "recommendation":
        return QueryContract(
            task_type=task_type,
            domain=domain,
            requested_count=requested_count,
            answer_entity_type="specific_product_or_style_category",
            entity_subtype="fashion_item",
            valid_item_rules=[
                "must be a specific clothing/accessory item or actionable style category",
                "must have source evidence or styling rationale",
            ],
            invalid_item_rules=[
                "generic headings do not count",
                "vague 'summer style' phrases do not count",
                "source titles do not count",
            ],
            required_evidence_fields=["name", "source_urls", "source_quality"],
            minimum_publishable_items=3,
            evidence_limited_allowed=True,
            exact_count_required=requested_count is not None,
        )

    if domain == "software_tools" and task_type == "recommendation":
        return QueryContract(
            task_type=task_type,
            domain=domain,
            requested_count=requested_count,
            answer_entity_type="software_product",
            entity_subtype="software_tool",
            valid_item_rules=[
                "must be a named software product, app, platform, or tool",
                "must have source evidence",
                "company product acceptable if source supports",
            ],
            invalid_item_rules=[
                "generic 'productivity tools' category phrases do not count",
                "section headings do not count",
                "source titles do not count",
            ],
            required_evidence_fields=["name", "source_urls", "source_quality"],
            minimum_publishable_items=3,
            evidence_limited_allowed=True,
            exact_count_required=requested_count is not None,
        )

    if domain == "finance" and task_type == "recommendation":
        return QueryContract(
            task_type=task_type,
            domain=domain,
            requested_count=requested_count,
            answer_entity_type="public_company_or_security",
            entity_subtype="public_company",
            valid_item_rules=[
                "must be framed as educational watchlist material, not buy advice",
                "must include risk and uncertainty context",
                "must have source evidence",
            ],
            invalid_item_rules=[
                "do not use buy/guaranteed-return language",
                "do not present unsupported price targets",
                "do not omit financial disclaimer",
                "direct buy/sell recommendations do not count",
            ],
            required_evidence_fields=["name", "source_urls", "source_quality", "risk_context"],
            minimum_publishable_items=3,
            evidence_limited_allowed=True,
            exact_count_required=requested_count is not None,
            safety_constraints=[
                "educational only",
                "not financial advice",
                "no direct buy/sell recommendation",
                "no performance prediction without sourced attribution",
            ],
        )

    if domain == "consumer_products" and task_type == "recommendation":
        asks_for_categories = any(t in lower for t in _CATEGORY_QUERY_TERMS)
        subtype = _infer_consumer_product_subtype(lower)
        return QueryContract(
            task_type=task_type,
            domain=domain,
            requested_count=requested_count,
            answer_entity_type="product_category" if asks_for_categories else "specific_product",
            entity_subtype=subtype,
            valid_item_rules=[
                "must be a specific named product, product model, or product line",
                "brand-only names do not count when specific products are required",
                "product categories count only when the prompt explicitly asks for "
                "categories/types/essentials",
                "must have source evidence",
            ],
            invalid_item_rules=[
                "generic category phrases do not count as product recommendations",
                "section headings do not count",
                "source titles do not count unless they contain a clean product name",
                "buying-guide, sale, shop, and navigation text do not count",
                "brand-only names do not count as specific product recommendations",
            ],
            required_evidence_fields=[
                "name",
                "source_urls",
                "source_titles",
                "source_quality",
                "evidence_spans",
                "supported_context",
            ],
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


def requires_candidate_ledger(contract: QueryContract) -> bool:
    """Return True when the query contract requires a candidate ledger."""
    if contract.task_type != "recommendation":
        return False
    if contract.requested_count is not None:
        return True
    return contract.answer_entity_type not in ("general_answer", "concept", "unknown")


def _contains_consumer_product_phrase(lower: str) -> bool:
    return any(term in lower for terms in _CONSUMER_PRODUCT_SUBTYPES.values() for term in terms)


def _infer_consumer_product_subtype(lower: str) -> Optional[str]:
    for subtype, terms in _CONSUMER_PRODUCT_SUBTYPES.items():
        if any(term in lower for term in terms):
            return subtype
    return None
