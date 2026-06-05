"""Tests for SoftwareToolsAdapter — named software product validation.

Covers:
- Extraction of known AI/student tools from source text
- Rejection of generic category phrases
- Rejection of section headings
- Candidate ledger quality behavior
"""

from __future__ import annotations

from blogagent.tools.domain_adapters.software_tools import SoftwareToolsAdapter
from blogagent.tools.recommendation_extractor import classify_candidate_entity
from blogagent.workflow.query_contract import build_query_contract


def _contract(topic: str = "best AI tools for students"):
    return build_query_contract(
        topic, is_recommendation=True, is_financial=False, requested_count=None
    )


def _adapter():
    return SoftwareToolsAdapter()


class TestSoftwareToolsKnownProducts:
    """Known named AI/student tools must be accepted."""

    def test_chatgpt_accepted(self):
        assert _adapter().is_valid_entity("ChatGPT", _contract()) is True

    def test_claude_accepted(self):
        assert _adapter().is_valid_entity("Claude", _contract()) is True

    def test_claude_ai_accepted(self):
        assert _adapter().is_valid_entity("Claude AI", _contract()) is True

    def test_perplexity_accepted(self):
        assert _adapter().is_valid_entity("Perplexity", _contract()) is True

    def test_notion_ai_accepted(self):
        assert _adapter().is_valid_entity("Notion AI", _contract()) is True

    def test_grammarly_accepted(self):
        assert _adapter().is_valid_entity("Grammarly", _contract()) is True

    def test_canva_accepted(self):
        assert _adapter().is_valid_entity("Canva", _contract()) is True

    def test_quizlet_accepted(self):
        assert _adapter().is_valid_entity("Quizlet", _contract()) is True

    def test_studley_ai_accepted(self):
        assert _adapter().is_valid_entity("Studley AI", _contract()) is True

    def test_google_gemini_accepted(self):
        assert _adapter().is_valid_entity("Google Gemini", _contract()) is True

    def test_microsoft_copilot_accepted(self):
        assert _adapter().is_valid_entity("Microsoft Copilot", _contract()) is True

    def test_wolfram_alpha_accepted(self):
        assert _adapter().is_valid_entity("Wolfram Alpha", _contract()) is True

    def test_elicit_accepted(self):
        assert _adapter().is_valid_entity("Elicit", _contract()) is True

    def test_consensus_accepted(self):
        assert _adapter().is_valid_entity("Consensus", _contract()) is True

    def test_otter_ai_accepted(self):
        assert _adapter().is_valid_entity("Otter.ai", _contract()) is True

    def test_khanmigo_accepted(self):
        assert _adapter().is_valid_entity("Khanmigo", _contract()) is True

    def test_duolingo_max_accepted(self):
        assert _adapter().is_valid_entity("Duolingo Max", _contract()) is True


class TestSoftwareToolsGenericRejection:
    """Generic category phrases must be rejected."""

    def test_ai_tools_rejected(self):
        assert _adapter().is_valid_entity("AI tools", _contract()) is False

    def test_study_tools_rejected(self):
        assert _adapter().is_valid_entity("study tools", _contract()) is False

    def test_education_technology_rejected(self):
        assert _adapter().is_valid_entity("education technology", _contract()) is False

    def test_learning_ai_rejected(self):
        assert _adapter().is_valid_entity("learning AI", _contract()) is False

    def test_productivity_tools_rejected(self):
        assert _adapter().is_valid_entity("productivity tools", _contract()) is False

    def test_student_tools_rejected(self):
        assert _adapter().is_valid_entity("student tools", _contract()) is False


class TestSoftwareToolsHeadingRejection:
    """Section headings must be rejected."""

    def test_navigating_ai_landscape_rejected(self):
        assert (
            _adapter().is_valid_entity(
                "Navigating the AI Landscape for Student Success", _contract()
            )
            is False
        )

    def test_how_we_chose_rejected(self):
        assert _adapter().is_valid_entity("How We Chose", _contract()) is False

    def test_buying_tips_rejected(self):
        assert _adapter().is_valid_entity("Buying or Choosing Tips", _contract()) is False

    def test_spotlight_on_rejected(self):
        result = _adapter().is_valid_entity("Spotlight on AI Tools for Learning", _contract())
        assert result is False

    def test_section_heading_rejected(self):
        assert _adapter().is_valid_entity("Introduction", _contract()) is False


class TestSoftwareToolsClassifyEntity:
    """classify_candidate_entity must use adapter for software_tools domain."""

    def test_chatgpt_classified_as_specific_product(self):
        contract = _contract()
        entity_type, is_specific, rejection = classify_candidate_entity("ChatGPT", contract)
        assert is_specific is True
        assert entity_type == "specific_product"
        assert rejection is None

    def test_grammarly_classified_as_specific_product(self):
        contract = _contract()
        entity_type, is_specific, rejection = classify_candidate_entity("Grammarly", contract)
        assert is_specific is True
        assert entity_type == "specific_product"

    def test_navigating_heading_classified_as_heading(self):
        contract = _contract()
        entity_type, is_specific, rejection = classify_candidate_entity(
            "Navigating the AI Landscape for Student Success", contract
        )
        assert is_specific is False
        assert rejection is not None

    def test_generic_ai_tools_rejected(self):
        contract = _contract()
        entity_type, is_specific, rejection = classify_candidate_entity("AI tools", contract)
        assert is_specific is False
        assert rejection is not None


class TestSoftwareToolsRejectionReason:
    """Rejection reasons must be informative."""

    def test_generic_category_rejection_reason(self):
        reason = _adapter().get_rejection_reason("AI tools", _contract())
        assert reason is not None
        assert "generic" in reason.lower() or "category" in reason.lower()

    def test_heading_rejection_reason(self):
        reason = _adapter().get_rejection_reason(
            "Navigating the AI Landscape for Student Success", _contract()
        )
        assert reason is not None
        assert "heading" in reason.lower() or "section" in reason.lower()

    def test_valid_product_no_rejection(self):
        reason = _adapter().get_rejection_reason("ChatGPT", _contract())
        assert reason is None


class TestSoftwareToolsEntityType:
    """classify_entity_type returns correct types."""

    def test_chatgpt_is_software_product(self):
        et = _adapter().classify_entity_type("ChatGPT", _contract())
        assert et == "software_product"

    def test_generic_is_category(self):
        et = _adapter().classify_entity_type("AI tools", _contract())
        assert et == "category"
