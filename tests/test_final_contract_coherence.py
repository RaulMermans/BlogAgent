"""Tests for final contract coherence invariants.

Verifies that:
1. allowed=0 with recommendations → draft compliance fails
2. allowed=0 → AnswerCountSnapshot status=failed, not satisfied
3. ledger failed → evidence_sufficiency.sufficient=False
4. Section headings not counted as recommendations in entity audit
5. Publish contract remains final authority
"""

from __future__ import annotations

from blogagent.agents.evidence_sufficiency import evaluate_evidence_sufficiency
from blogagent.tools.article_entity_audit import (
    EntityAudit,
    build_answer_count_snapshot,
)
from blogagent.tools.draft_candidate_compliance import (
    check_draft_candidate_compliance,
)
from blogagent.workflow.query_contract import build_query_contract


def _rec_contract(topic: str = "best AI tools for students"):
    return build_query_contract(
        topic, is_recommendation=True, is_financial=False, requested_count=None
    )


def _finance_contract(topic: str = "best energy stocks to watch in 2026"):
    return build_query_contract(
        topic, is_recommendation=True, is_financial=True, requested_count=None
    )


def _explainer_contract():
    return build_query_contract(
        "why elephants are large", is_recommendation=False, is_financial=False, requested_count=None
    )


def _audit(article_count: int, grounded_count: int) -> EntityAudit:
    return EntityAudit(
        article_entities_count=article_count,
        grounded_entities_count=grounded_count,
        allowed_entities_count=0,
        passes=False,
    )


# ---------------------------------------------------------------------------
# Draft compliance invariants
# ---------------------------------------------------------------------------


class TestDraftComplianceInvariants:
    """Draft compliance hard-fail rules when allowed=0."""

    def test_allowed_zero_recommended_positive_fails(self):
        """allowed=0 but article has recommendations → compliance must fail."""
        contract = _rec_contract()
        article = (
            "# Best AI Tools\n\n## Quick Picks\n\n"
            "- **Best Overall:** ChatGPT\n"
            "- **Best Writing:** Grammarly\n\n"
            "## ChatGPT\n\nExcellent tool.\n\n"
            "## Final Takeaway\n\nGreat options.\n"
        )
        result = check_draft_candidate_compliance(
            article_markdown=article,
            allowed_candidates=[],  # zero allowed candidates
            query_contract=contract,
            minimum_publishable_items=3,
        )
        assert result.passes is False
        assert result.failure_reason is not None
        reason = result.failure_reason.lower()
        assert "zero allowed" in reason or "unsupported" in reason

    def test_allowed_zero_no_recommendations_passes(self):
        """allowed=0 and no recommendations → compliance passes (no article generated)."""
        contract = _rec_contract()
        article = (
            "# AI Tools Report\n\nNo validated tools were found in the evidence. "
            "Sources were searched but produced no extractable named software products.\n"
        )
        result = check_draft_candidate_compliance(
            article_markdown=article,
            allowed_candidates=[],
            query_contract=contract,
            minimum_publishable_items=3,
        )
        assert result.passes is True

    def test_allowed_zero_seven_recommendations_fails(self):
        """The impossible state: allowed=0 but article has 7 recommendations."""
        contract = _finance_contract()
        names = [
            "Brookfield Renewable",
            "American Electric Power",
            "Baker Hughes",
            "Bloom Energy",
            "NextEra Energy",
            "Chevron",
            "Exxon Mobil",
        ]
        quick_picks = "\n".join(f"- **Best pick:** {n}" for n in names)
        article = (
            "# Best Energy Stocks\n\n## Quick Picks\n\n"
            + quick_picks
            + "\n\n## Final Takeaway\n\nReview carefully.\n"
        )
        result = check_draft_candidate_compliance(
            article_markdown=article,
            allowed_candidates=[],
            query_contract=contract,
        )
        assert result.passes is False, "allowed=0 but 7 recommendations must FAIL compliance"
        reason = (result.failure_reason or "").lower()
        assert "zero allowed" in reason or "unsupported" in reason


# ---------------------------------------------------------------------------
# AnswerCountSnapshot invariants
# ---------------------------------------------------------------------------


class TestAnswerCountSnapshotInvariants:
    """AnswerCountSnapshot cannot be satisfied when allowed=0."""

    def test_allowed_zero_article_seven_grounded_seven_is_failed(self):
        """The impossible state: allowed=0, article=7, grounded=7 → must be FAILED."""
        contract = _rec_contract()
        snapshot = build_answer_count_snapshot(
            requested_count=None,
            allowed_candidates=[],  # zero allowed
            entity_audit=_audit(7, 7),  # article has 7 recommendations
            query_contract=contract,
            minimum_publishable_items=3,
        )
        assert snapshot.count_status == "failed", (
            f"Expected failed but got {snapshot.count_status!r} — "
            "allowed=0 with article=7 is incoherent"
        )
        assert snapshot.allowed_candidates_count == 0

    def test_allowed_zero_article_zero_is_failed(self):
        """allowed=0, article=0 → failed (no candidates, no publishable content)."""
        contract = _rec_contract()
        snapshot = build_answer_count_snapshot(
            requested_count=None,
            allowed_candidates=[],
            entity_audit=_audit(0, 0),
            query_contract=contract,
            minimum_publishable_items=3,
        )
        assert snapshot.count_status == "failed"
        assert snapshot.failure_reason is not None

    def test_allowed_zero_compliance_false_is_failed(self):
        """Compliance=False with allowed=0 → count_status=failed."""
        contract = _rec_contract()

        class FakeCompliance:
            passes = False
            recommended_count = 5
            failure_reason = "zero allowed candidates"

        snapshot = build_answer_count_snapshot(
            requested_count=None,
            allowed_candidates=[],
            entity_audit=_audit(5, 5),
            query_contract=contract,
            minimum_publishable_items=3,
            draft_candidate_compliance=FakeCompliance(),
        )
        assert snapshot.count_status == "failed"

    def test_not_applicable_for_explainer(self):
        """Non-recommendation topics are always not_applicable."""
        contract = _explainer_contract()
        snapshot = build_answer_count_snapshot(
            requested_count=None,
            allowed_candidates=[],
            entity_audit=None,
            query_contract=contract,
        )
        assert snapshot.count_status == "not_applicable"

    def test_satisfied_requires_allowed_candidates(self):
        """satisfied requires allowed_candidates_count >= minimum."""
        contract = _rec_contract()
        allowed = [{"name": f"Tool {i}", "usable": True} for i in range(4)]
        snapshot = build_answer_count_snapshot(
            requested_count=None,
            allowed_candidates=allowed,
            entity_audit=_audit(4, 4),
            query_contract=contract,
            minimum_publishable_items=3,
        )
        # With 4 allowed and 4 in article, this should be satisfied
        assert snapshot.count_status in ("satisfied", "evidence_limited")
        assert snapshot.allowed_candidates_count == 4


# ---------------------------------------------------------------------------
# Evidence sufficiency invariants
# ---------------------------------------------------------------------------


class TestEvidenceSufficiencyInvariants:
    """Evidence sufficiency must reflect candidate ledger failures."""

    def test_supported_count_zero_caps_score(self):
        """supported_count=0 for recommendation → sufficient=False."""
        result = evaluate_evidence_sufficiency(
            topic="best AI tools for students",
            requested_count=None,
            is_recommendation=True,
            is_financial=False,
            source_quality_scores=[
                {"url": "https://example.com", "quality": "high"},
                {"url": "https://example2.com", "quality": "medium"},
            ],
            evidence_table=[],
            enrichment_already_ran=False,
            recommendation_candidates=[{"usable": False}, {"usable": False}],
        )
        assert result.sufficient is False, (
            f"Expected not sufficient but got sufficient={result.sufficient}, score={result.score}"
        )
        assert result.score <= 59, f"Score must be <= 59 when supported_count=0, got {result.score}"

    def test_supported_count_nonzero_can_be_sufficient(self):
        """supported_count > 0 → can be sufficient."""
        result = evaluate_evidence_sufficiency(
            topic="best AI tools for students",
            requested_count=None,
            is_recommendation=True,
            is_financial=False,
            source_quality_scores=[
                {"url": "https://allure.com", "quality": "high"},
                {"url": "https://byrdie.com", "quality": "high"},
            ],
            evidence_table=[],
            enrichment_already_ran=False,
            recommendation_candidates=[
                {"usable": True, "name": "ChatGPT"},
                {"usable": True, "name": "Grammarly"},
                {"usable": True, "name": "Canva"},
            ],
        )
        assert result.sufficient is True
        assert result.supported_count == 3

    def test_non_recommendation_bypasses_candidate_check(self):
        """Non-recommendation topics bypass the candidate ledger check."""
        result = evaluate_evidence_sufficiency(
            topic="how elephants regulate temperature",
            requested_count=None,
            is_recommendation=False,
            is_financial=False,
            source_quality_scores=[
                {"url": "https://wikipedia.org", "quality": "high"},
            ],
            evidence_table=[],
            enrichment_already_ran=False,
            recommendation_candidates=None,  # No candidates for explainer
        )
        assert result.sufficient is True


# ---------------------------------------------------------------------------
# Entity audit heading rejection
# ---------------------------------------------------------------------------


class TestEntityAuditHeadingRejection:
    """Section headings must not be counted as recommendation entities."""

    def test_software_heading_not_a_product(self):
        """'Navigating the AI Landscape for Student Success' is not a software product."""
        from blogagent.tools.domain_adapters.software_tools import SoftwareToolsAdapter

        adapter = SoftwareToolsAdapter()
        contract = _rec_contract()
        assert (
            adapter.is_valid_entity("Navigating the AI Landscape for Student Success", contract)
            is False
        )

    def test_finance_heading_not_a_company(self):
        """'Spotlight on Key Energy Players for 2026' is not a company."""
        from blogagent.tools.domain_adapters.finance import FinanceAdapter

        adapter = FinanceAdapter()
        contract = _finance_contract()
        assert (
            adapter.is_valid_entity("Spotlight on Key Energy Players for 2026", contract) is False
        )

    def test_our_approach_heading_not_a_company(self):
        """'Our Approach to Identifying Energy Opportunities' is not a company."""
        from blogagent.tools.domain_adapters.finance import FinanceAdapter

        adapter = FinanceAdapter()
        contract = _finance_contract()
        assert (
            adapter.is_valid_entity("Our Approach to Identifying Energy Opportunities", contract)
            is False
        )


# ---------------------------------------------------------------------------
# Coherence between compliance, snapshot, and publish contract
# ---------------------------------------------------------------------------


class TestEndToEndCoherence:
    """Verify the coherence chain: compliance → snapshot → publish contract."""

    def test_allowed_zero_chain_is_coherent(self):
        """
        When allowed=0:
        - compliance must fail
        - snapshot must be failed
        - these states are mutually consistent (no contradictions)
        """
        contract = _rec_contract()
        article = (
            "# Best AI Tools\n\n## Quick Picks\n\n"
            "- **Best:** ChatGPT\n- **Writing:** Grammarly\n\n"
            "## Final Takeaway\nGreat tools.\n"
        )

        # Step 1: compliance
        compliance = check_draft_candidate_compliance(
            article_markdown=article,
            allowed_candidates=[],
            query_contract=contract,
            minimum_publishable_items=3,
        )
        assert compliance.passes is False

        # Step 2: snapshot must also be failed
        snapshot = build_answer_count_snapshot(
            requested_count=None,
            allowed_candidates=[],
            entity_audit=_audit(2, 2),
            query_contract=contract,
            minimum_publishable_items=3,
            draft_candidate_compliance=compliance,
        )
        assert snapshot.count_status == "failed"

        # Step 3: verify no impossible state exists
        assert not (
            compliance.passes is True
            and compliance.allowed_count == 0
            and compliance.recommended_count > 0
        ), "Impossible state: passes=True with allowed=0 and recommended>0"

        assert not (
            snapshot.count_status == "satisfied" and snapshot.allowed_candidates_count == 0
        ), "Impossible state: satisfied with allowed=0"
