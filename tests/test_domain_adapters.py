"""Tests for the domain adapter architecture."""

from __future__ import annotations

from blogagent.tools.domain_adapters import get_adapter
from blogagent.tools.domain_adapters.beauty_fragrance import BeautyFragranceAdapter
from blogagent.tools.domain_adapters.beauty_makeup import BeautyMakeupAdapter
from blogagent.tools.domain_adapters.finance import FinanceAdapter
from blogagent.tools.domain_adapters.general import GeneralAdapter
from blogagent.tools.domain_adapters.software_tools import SoftwareToolsAdapter
from blogagent.workflow.query_contract import build_query_contract

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fragrance_contract(topic: str = "7 best parfums for summer"):
    return build_query_contract(
        topic, is_recommendation=True, is_financial=False, requested_count=7
    )


def _software_contract(topic: str = "best AI tools for students"):
    return build_query_contract(
        topic, is_recommendation=True, is_financial=False, requested_count=None
    )


def _finance_contract(topic: str = "best energy stocks to watch in 2026"):
    return build_query_contract(
        topic, is_recommendation=True, is_financial=True, requested_count=None
    )


def _explainer_contract(topic: str = "why elephants are the heaviest land animals"):
    return build_query_contract(
        topic, is_recommendation=False, is_financial=False, requested_count=None
    )


# ---------------------------------------------------------------------------
# get_adapter
# ---------------------------------------------------------------------------


def test_get_adapter_returns_fragrance_adapter():
    adapter = get_adapter("beauty_fragrance")
    assert isinstance(adapter, BeautyFragranceAdapter)


def test_get_adapter_returns_software_adapter():
    adapter = get_adapter("software_tools")
    assert isinstance(adapter, SoftwareToolsAdapter)


def test_get_adapter_unknown_falls_back_to_general():
    adapter = get_adapter("unknown_domain")
    assert isinstance(adapter, GeneralAdapter)


# ---------------------------------------------------------------------------
# Base adapter — universal rejection rules
# ---------------------------------------------------------------------------


class TestBaseRejectionRules:
    def test_section_heading_is_rejected(self):
        adapter = get_adapter("beauty_fragrance")
        assert adapter.looks_like_section_heading("How We Chose") is True

    def test_buying_tips_is_rejected(self):
        adapter = get_adapter("beauty_fragrance")
        assert adapter.looks_like_section_heading("Buying Tips") is True

    def test_conclusion_is_rejected(self):
        adapter = get_adapter("general")
        assert adapter.looks_like_section_heading("Conclusion") is True

    def test_url_is_rejected(self):
        adapter = get_adapter("beauty_fragrance")
        assert adapter.looks_like_url_or_citation("https://allure.com") is True

    def test_citation_number_is_rejected(self):
        adapter = get_adapter("beauty_fragrance")
        assert adapter.looks_like_url_or_citation("[1]") is True

    def test_entity_cluster_rejected(self):
        adapter = get_adapter("beauty_fragrance")
        # This string has 4 known brands — should be a cluster
        assert adapter.looks_like_entity_cluster("ARMANI PRADA Paco Rabanne CREED CALVIN") is True

    def test_product_not_entity_cluster(self):
        adapter = get_adapter("beauty_fragrance")
        assert adapter.looks_like_entity_cluster("Ouai Melrose Place Eau de Parfum") is False


# ---------------------------------------------------------------------------
# BeautyFragranceAdapter
# ---------------------------------------------------------------------------


class TestBeautyFragranceAdapter:
    def setup_method(self):
        self.adapter = BeautyFragranceAdapter()
        self.contract = _fragrance_contract()

    def test_valid_specific_product(self):
        assert (
            self.adapter.is_valid_entity("Ouai Melrose Place Eau de Parfum", self.contract)
            is True
        )

    def test_valid_dolce_gabbana_product(self):
        assert (
            self.adapter.is_valid_entity(
                "Dolce & Gabbana Light Blue Eau de Toilette", self.contract
            )
            is True
        )

    def test_valid_maison_margiela(self):
        assert (
            self.adapter.is_valid_entity(
                "Maison Margiela Replica Afternoon Delight Eau de Toilette", self.contract
            )
            is True
        )

    def test_valid_tom_ford_product(self):
        assert self.adapter.is_valid_entity("Tom Ford Soleil Blanc", self.contract) is True

    def test_valid_jo_malone_product(self):
        assert (
            self.adapter.is_valid_entity("Jo Malone London Wood Sage & Sea Salt", self.contract)
            is True
        )

    def test_valid_glossier_product(self):
        assert (
            self.adapter.is_valid_entity("Glossier You Fleur Eau de Parfum", self.contract)
            is True
        )

    def test_brand_only_kilian_rejected(self):
        assert self.adapter.is_valid_entity("Kilian", self.contract) is False

    def test_brand_only_glossier_rejected(self):
        assert self.adapter.is_valid_entity("Glossier", self.contract) is False

    def test_brand_only_sol_de_janeiro_rejected(self):
        assert self.adapter.is_valid_entity("Sol de Janeiro", self.contract) is False

    def test_entity_cluster_armani_rejected(self):
        assert (
            self.adapter.is_valid_entity(
                "ARMANI PRADA Paco Rabanne CREED CALVIN", self.contract
            )
            is False
        )

    def test_entity_cluster_dior_rejected(self):
        assert (
            self.adapter.is_valid_entity(
                "DIOR Yves Saint Laurent GUCCI Dolce", self.contract
            )
            is False
        )

    def test_section_heading_how_we_chose_rejected(self):
        assert (
            self.adapter.is_valid_entity(
                "How We Chose Our Top Summer Parfums", self.contract
            )
            is False
        )

    def test_section_heading_choosing_rejected(self):
        assert (
            self.adapter.is_valid_entity("Choosing Your Signature Summer Scent", self.contract)
            is False
        )

    def test_category_phrase_summer_parfums_rejected(self):
        # "Summer parfums" is a category, not a product
        assert self.adapter.is_valid_entity("Summer parfums", self.contract) is False

    def test_entity_cluster_rejection_reason(self):
        reason = self.adapter.get_rejection_reason(
            "ARMANI PRADA Paco Rabanne CREED CALVIN", self.contract
        )
        assert reason is not None
        assert "cluster" in reason.lower() or "brand" in reason.lower()

    def test_brand_only_rejection_reason(self):
        reason = self.adapter.get_rejection_reason("Kilian", self.contract)
        assert reason is not None
        assert "brand" in reason.lower()

    def test_classify_specific_product(self):
        et = self.adapter.classify_entity_type("Ouai Melrose Place Eau de Parfum", self.contract)
        assert et == "specific_product"

    def test_classify_brand_only(self):
        et = self.adapter.classify_entity_type("Kilian", self.contract)
        assert et == "brand"


# ---------------------------------------------------------------------------
# BeautyMakeupAdapter
# ---------------------------------------------------------------------------


class TestBeautyMakeupAdapter:
    def setup_method(self):
        self.adapter = BeautyMakeupAdapter()
        self.contract = build_query_contract(
            "best festival makeup for summer",
            is_recommendation=True,
            is_financial=False,
            requested_count=None,
        )

    def test_specific_product_valid(self):
        assert (
            self.adapter.is_valid_entity(
                "Rare Beauty Soft Pinch Liquid Blush", self.contract
            )
            is True
        )

    def test_setting_spray_valid(self):
        assert (
            self.adapter.is_valid_entity(
                "Charlotte Tilbury Airbrush Flawless Setting Spray", self.contract
            )
            is True
        )

    def test_brand_only_rejected(self):
        assert self.adapter.is_valid_entity("Rare Beauty", self.contract) is False

    def test_section_heading_rejected(self):
        assert self.adapter.is_valid_entity("How We Chose", self.contract) is False


# ---------------------------------------------------------------------------
# SoftwareToolsAdapter
# ---------------------------------------------------------------------------


class TestSoftwareToolsAdapter:
    def setup_method(self):
        self.adapter = SoftwareToolsAdapter()
        self.contract = _software_contract()

    def test_notion_ai_valid(self):
        assert self.adapter.is_valid_entity("Notion AI", self.contract) is True

    def test_perplexity_valid(self):
        assert self.adapter.is_valid_entity("Perplexity", self.contract) is True

    def test_grammarly_valid(self):
        assert self.adapter.is_valid_entity("Grammarly", self.contract) is True

    def test_chatgpt_valid(self):
        assert self.adapter.is_valid_entity("ChatGPT", self.contract) is True

    def test_canva_valid(self):
        assert self.adapter.is_valid_entity("Canva", self.contract) is True

    def test_generic_category_rejected(self):
        assert self.adapter.is_valid_entity("productivity tools", self.contract) is False

    def test_section_heading_rejected(self):
        assert self.adapter.is_valid_entity("How We Chose", self.contract) is False


# ---------------------------------------------------------------------------
# FinanceAdapter
# ---------------------------------------------------------------------------


class TestFinanceAdapter:
    def setup_method(self):
        self.adapter = FinanceAdapter()
        self.contract = _finance_contract()

    def test_known_company_valid(self):
        assert self.adapter.is_valid_entity("Apple", self.contract) is True

    def test_known_etf_valid(self):
        assert self.adapter.is_valid_entity("XLE", self.contract) is True

    def test_safety_constraints_exist(self):
        assert len(self.contract.safety_constraints) > 0

    def test_buy_sell_language_rejected(self):
        assert self.adapter.is_valid_entity("buy now", self.contract) is False

    def test_finance_domain(self):
        assert self.contract.domain == "finance"

    def test_entity_subtype(self):
        assert self.contract.entity_subtype == "public_company"


# ---------------------------------------------------------------------------
# GeneralAdapter
# ---------------------------------------------------------------------------


class TestGeneralAdapter:
    def setup_method(self):
        self.adapter = GeneralAdapter()
        self.contract = _explainer_contract()

    def test_explainer_contract_no_ledger_required(self):
        from blogagent.workflow.query_contract import requires_candidate_ledger
        assert requires_candidate_ledger(self.contract) is False

    def test_section_heading_still_rejected(self):
        assert self.adapter.looks_like_section_heading("Conclusion") is True
