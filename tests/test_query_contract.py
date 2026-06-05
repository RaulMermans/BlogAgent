from __future__ import annotations

from blogagent.workflow.query_contract import build_query_contract, requires_candidate_ledger


def test_7_best_parfums_contract_is_product_recommendation():
    contract = build_query_contract(
        "7 best parfums for summer",
        is_recommendation=True,
        is_financial=False,
        requested_count=7,
    )
    assert contract.task_type == "recommendation"
    assert contract.domain == "beauty_fragrance"
    assert contract.answer_entity_type == "specific_product"
    assert contract.entity_subtype == "fragrance_product"
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
    assert contract.entity_subtype is None


def test_elephant_question_is_explainer_general():
    contract = build_query_contract(
        "why elephants are heavy",
        is_recommendation=False,
        is_financial=False,
        requested_count=None,
    )
    assert contract.task_type == "explainer"
    assert contract.domain == "general"
    assert requires_candidate_ledger(contract) is False


def test_energy_stocks_contract_is_finance_recommendation():
    contract = build_query_contract(
        "best energy stocks to watch",
        is_recommendation=True,
        is_financial=True,
        requested_count=None,
    )
    assert contract.task_type == "recommendation"
    assert contract.domain == "finance"
    assert contract.answer_entity_type == "public_company_or_security"
    assert contract.entity_subtype == "public_company"
    assert any("educational" in rule for rule in contract.valid_item_rules)
    assert len(contract.safety_constraints) > 0


def test_makeup_contract_is_product_recommendation():
    contract = build_query_contract(
        "best festival makeup for summer",
        is_recommendation=True,
        is_financial=False,
        requested_count=None,
    )
    assert contract.domain == "beauty_makeup"
    assert contract.answer_entity_type == "specific_product"
    assert contract.entity_subtype == "makeup_product"


def test_makeup_essentials_allows_category():
    contract = build_query_contract(
        "best makeup essentials kit",
        is_recommendation=True,
        is_financial=False,
        requested_count=None,
    )
    assert contract.domain == "beauty_makeup"
    assert contract.answer_entity_type == "specific_product_or_product_category"


def test_ai_tools_contract_is_software_recommendation():
    contract = build_query_contract(
        "best AI tools for students",
        is_recommendation=True,
        is_financial=False,
        requested_count=None,
    )
    assert contract.domain == "software_tools"
    assert contract.answer_entity_type == "software_product"
    assert contract.entity_subtype == "software_tool"
    assert requires_candidate_ledger(contract) is True


def test_requires_candidate_ledger_true_for_recommendation():
    contract = build_query_contract(
        "7 best parfums for summer",
        is_recommendation=True,
        is_financial=False,
        requested_count=7,
    )
    assert requires_candidate_ledger(contract) is True


def test_requires_candidate_ledger_false_for_explainer():
    contract = build_query_contract(
        "why elephants are heavy",
        is_recommendation=False,
        is_financial=False,
        requested_count=None,
    )
    assert requires_candidate_ledger(contract) is False


def test_finance_safety_constraints():
    contract = build_query_contract(
        "best energy stocks to watch in 2026",
        is_recommendation=True,
        is_financial=True,
        requested_count=None,
    )
    constraints = contract.safety_constraints
    assert any("educational" in c.lower() for c in constraints)
    assert any("financial advice" in c.lower() for c in constraints)
    assert any("buy/sell" in c.lower() for c in constraints)


def test_affordable_luxury_watches_falls_back_to_consumer_products():
    contract = build_query_contract(
        "5 best affordable luxury watches",
        is_recommendation=True,
        is_financial=False,
        requested_count=5,
    )
    assert contract.task_type == "recommendation"
    assert contract.domain == "consumer_products"
    assert contract.answer_entity_type == "specific_product"
    assert contract.entity_subtype == "watch"
    assert contract.requested_count == 5
    assert contract.minimum_publishable_items == 3
    assert requires_candidate_ledger(contract) is True


def test_carry_on_luggage_falls_back_to_consumer_products():
    contract = build_query_contract(
        "best carry-on luggage for Europe",
        is_recommendation=True,
        is_financial=False,
        requested_count=None,
    )
    assert contract.domain == "consumer_products"
    assert contract.answer_entity_type == "specific_product"
    assert contract.entity_subtype == "luggage"


def test_beginner_cameras_falls_back_to_consumer_products():
    contract = build_query_contract(
        "best cameras for beginners",
        is_recommendation=True,
        is_financial=False,
        requested_count=None,
    )
    assert contract.domain == "consumer_products"
    assert contract.answer_entity_type == "specific_product"
    assert contract.entity_subtype == "camera"


def test_office_chairs_under_300_falls_back_to_consumer_products():
    contract = build_query_contract(
        "best office chairs under 300",
        is_recommendation=True,
        is_financial=False,
        requested_count=None,
    )
    assert contract.domain == "consumer_products"
    assert contract.answer_entity_type == "specific_product"
    assert contract.entity_subtype == "office_chair"


def test_leather_sneakers_not_general_answer():
    contract = build_query_contract(
        "best leather sneakers for men",
        is_recommendation=True,
        is_financial=False,
        requested_count=None,
    )
    assert contract.domain in ("fashion_lifestyle", "consumer_products")
    assert contract.answer_entity_type != "general_answer"


def test_watches_explainer_does_not_require_ledger():
    contract = build_query_contract(
        "why watches are expensive",
        is_recommendation=False,
        is_financial=False,
        requested_count=None,
    )
    assert contract.task_type == "explainer"
    assert contract.domain == "general"
    assert contract.answer_entity_type == "general_answer"
    assert requires_candidate_ledger(contract) is False


def test_counted_recommendation_cannot_be_general_answer():
    contract = build_query_contract(
        "5 best affordable luxury watches",
        is_recommendation=True,
        is_financial=False,
        requested_count=5,
    )
    assert not (
        contract.domain == "general" and contract.answer_entity_type == "general_answer"
    )
