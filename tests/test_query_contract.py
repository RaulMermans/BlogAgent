from __future__ import annotations

from blogagent.workflow.query_contract import build_query_contract


def test_7_best_parfums_contract_is_product_recommendation():
    contract = build_query_contract(
        "7 best parfums for summer",
        is_recommendation=True,
        is_financial=False,
        requested_count=7,
    )
    assert contract.task_type == "recommendation"
    assert contract.domain == "beauty_fragrance"
    assert contract.answer_entity_type == "specific_fragrance_product"
    assert contract.requested_count == 7
    assert contract.exact_count_required is True
    assert contract.minimum_publishable_items == 3


def test_perfume_brand_query_allows_brand_entity():
    contract = build_query_contract(
        "best perfume brands for summer",
        is_recommendation=True,
        is_financial=False,
        requested_count=None,
    )
    assert contract.domain == "beauty_fragrance"
    assert contract.answer_entity_type == "fragrance_brand"


def test_elephant_question_is_explainer_general():
    contract = build_query_contract(
        "why elephants are heavy",
        is_recommendation=False,
        is_financial=False,
        requested_count=None,
    )
    assert contract.task_type == "explainer"
    assert contract.domain == "general"


def test_energy_stocks_contract_is_finance_recommendation():
    contract = build_query_contract(
        "best energy stocks to watch",
        is_recommendation=True,
        is_financial=True,
        requested_count=None,
    )
    assert contract.task_type == "recommendation"
    assert contract.domain == "finance"
    assert contract.answer_entity_type == "financial_security_watchlist"
    assert any("educational" in rule for rule in contract.valid_item_rules)
