"""Tests for FinanceAdapter — public company/security validation.

Covers:
- Extraction of known energy companies and ETFs
- Rejection of generic category phrases
- Rejection of article section headings
- Financial safety constraints remain active
"""

from __future__ import annotations

from blogagent.tools.domain_adapters.finance import FinanceAdapter
from blogagent.tools.recommendation_extractor import classify_candidate_entity
from blogagent.workflow.query_contract import build_query_contract


def _contract(topic: str = "best energy stocks to watch in 2026"):
    return build_query_contract(
        topic, is_recommendation=True, is_financial=True, requested_count=None
    )


def _adapter():
    return FinanceAdapter()


class TestFinanceAdapterKnownCompanies:
    """Known energy/finance companies must be accepted."""

    def test_brookfield_renewable_accepted(self):
        assert _adapter().is_valid_entity("Brookfield Renewable", _contract()) is True

    def test_american_electric_power_accepted(self):
        assert _adapter().is_valid_entity("American Electric Power", _contract()) is True

    def test_american_electric_power_company_accepted(self):
        assert _adapter().is_valid_entity("American Electric Power Company", _contract()) is True

    def test_baker_hughes_accepted(self):
        assert _adapter().is_valid_entity("Baker Hughes", _contract()) is True

    def test_baker_hughes_co_accepted(self):
        assert _adapter().is_valid_entity("Baker Hughes Co", _contract()) is True

    def test_bloom_energy_accepted(self):
        assert _adapter().is_valid_entity("Bloom Energy", _contract()) is True

    def test_nextera_energy_accepted(self):
        assert _adapter().is_valid_entity("NextEra Energy", _contract()) is True

    def test_chevron_accepted(self):
        assert _adapter().is_valid_entity("Chevron", _contract()) is True

    def test_exxon_mobil_accepted(self):
        assert _adapter().is_valid_entity("Exxon Mobil", _contract()) is True

    def test_enphase_energy_accepted(self):
        assert _adapter().is_valid_entity("Enphase Energy", _contract()) is True

    def test_first_solar_accepted(self):
        assert _adapter().is_valid_entity("First Solar", _contract()) is True

    def test_kinder_morgan_accepted(self):
        assert _adapter().is_valid_entity("Kinder Morgan", _contract()) is True

    def test_xle_etf_accepted(self):
        assert _adapter().is_valid_entity("XLE", _contract()) is True


class TestFinanceAdapterCategoryRejection:
    """Generic category phrases must be rejected."""

    def test_energy_stocks_rejected(self):
        assert _adapter().is_valid_entity("energy stocks", _contract()) is False

    def test_renewable_energy_leaders_rejected(self):
        assert _adapter().is_valid_entity("renewable energy leaders", _contract()) is False

    def test_green_energy_stocks_rejected(self):
        assert _adapter().is_valid_entity("green energy stocks", _contract()) is False

    def test_top_energy_companies_rejected(self):
        assert _adapter().is_valid_entity("top energy companies", _contract()) is False

    def test_investment_tips_rejected(self):
        assert _adapter().is_valid_entity("investment tips", _contract()) is False

    def test_energy_sector_rejected(self):
        assert _adapter().is_valid_entity("energy sector", _contract()) is False


class TestFinanceAdapterHeadingRejection:
    """Editorial section headings must be rejected as company names."""

    def test_shifting_sands_heading_rejected(self):
        assert (
            _adapter().is_valid_entity(
                "The Shifting Sands of Energy: Opportunities in 2026", _contract()
            )
            is False
        )

    def test_our_approach_heading_rejected(self):
        assert (
            _adapter().is_valid_entity(
                "Our Approach to Identifying Energy Opportunities", _contract()
            )
            is False
        )

    def test_spotlight_heading_rejected(self):
        assert (
            _adapter().is_valid_entity("Spotlight on Key Energy Players for 2026", _contract())
            is False
        )

    def test_opportunities_in_2026_rejected(self):
        # This is an article heading fragment, not a company name
        assert _adapter().is_valid_entity("Opportunities in 2026", _contract()) is False

    def test_how_we_chose_rejected(self):
        assert _adapter().is_valid_entity("How We Chose", _contract()) is False


class TestFinanceAdapterSafetyConstraints:
    """Financial safety constraints must remain active."""

    def test_buy_sell_language_rejected(self):
        assert _adapter().is_valid_entity("buy now", _contract()) is False

    def test_guaranteed_returns_rejected(self):
        assert _adapter().is_valid_entity("guaranteed return picks", _contract()) is False

    def test_safety_constraints_present_in_contract(self):
        contract = _contract()
        assert len(contract.safety_constraints) > 0
        assert any("not financial advice" in c for c in contract.safety_constraints)

    def test_rejection_rules_include_safety(self):
        rules = _adapter().get_rejection_rules(_contract())
        assert any("buy" in r.lower() or "safety" in r.lower() for r in rules)


class TestFinanceAdapterClassifyEntity:
    """classify_candidate_entity uses adapter for finance domain."""

    def test_known_company_classified_as_specific_product(self):
        contract = _contract()
        entity_type, is_specific, rejection = classify_candidate_entity(
            "Brookfield Renewable", contract
        )
        assert is_specific is True
        assert entity_type == "specific_product"
        assert rejection is None

    def test_heading_not_classified_as_company(self):
        contract = _contract()
        entity_type, is_specific, rejection = classify_candidate_entity(
            "The Shifting Sands of Energy: Opportunities in 2026", contract
        )
        assert is_specific is False
        assert rejection is not None

    def test_category_phrase_not_classified_as_company(self):
        contract = _contract()
        entity_type, is_specific, rejection = classify_candidate_entity("energy stocks", contract)
        assert is_specific is False

    def test_opportunities_in_2026_not_a_company(self):
        contract = _contract()
        entity_type, is_specific, rejection = classify_candidate_entity(
            "Opportunities in 2026", contract
        )
        assert is_specific is False


class TestFinanceAdapterRejectionReason:
    """Rejection reasons must be informative."""

    def test_category_phrase_rejection_reason(self):
        reason = _adapter().get_rejection_reason("energy stocks", _contract())
        assert reason is not None
        assert "category" in reason.lower() or "generic" in reason.lower()

    def test_heading_rejection_reason(self):
        reason = _adapter().get_rejection_reason(
            "The Shifting Sands of Energy: Opportunities in 2026", _contract()
        )
        assert reason is not None
        assert "heading" in reason.lower() or "section" in reason.lower()

    def test_valid_company_no_rejection(self):
        reason = _adapter().get_rejection_reason("Brookfield Renewable", _contract())
        assert reason is None

    def test_buy_sell_rejection_reason(self):
        reason = _adapter().get_rejection_reason("buy now", _contract())
        assert reason is not None
        assert "buy" in reason.lower() or "safety" in reason.lower()
