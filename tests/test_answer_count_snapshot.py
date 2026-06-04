"""Tests for the AnswerCountSnapshot and count status logic."""

from __future__ import annotations

from blogagent.tools.article_entity_audit import (
    EntityAudit,
    build_answer_count_snapshot,
)
from blogagent.workflow.query_contract import build_query_contract

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fragrance_contract(count: int = 7):
    return build_query_contract(
        f"{count} best parfums for summer",
        is_recommendation=True,
        is_financial=False,
        requested_count=count,
    )


def _explainer_contract():
    return build_query_contract(
        "why elephants are heavy",
        is_recommendation=False,
        is_financial=False,
        requested_count=None,
    )


def _audit(article_count: int, grounded_count: int, passes: bool = True) -> EntityAudit:
    return EntityAudit(
        article_entities_count=article_count,
        grounded_entities_count=grounded_count,
        allowed_entities_count=grounded_count,
        passes=passes,
    )


def _allowed(count: int) -> list[dict]:
    return [{"name": f"Product {i}", "usable": True} for i in range(count)]


# ---------------------------------------------------------------------------
# build_answer_count_snapshot
# ---------------------------------------------------------------------------


class TestBuildAnswerCountSnapshot:
    def test_not_applicable_for_explainer(self):
        snapshot = build_answer_count_snapshot(
            requested_count=None,
            allowed_candidates=[],
            entity_audit=None,
            query_contract=_explainer_contract(),
        )
        assert snapshot.count_status == "not_applicable"

    def test_satisfied_when_article_meets_requested(self):
        """requested=7, allowed=7, article=7, grounded=7 → satisfied"""
        snapshot = build_answer_count_snapshot(
            requested_count=7,
            allowed_candidates=_allowed(7),
            entity_audit=_audit(7, 7),
            query_contract=_fragrance_contract(7),
        )
        assert snapshot.count_status == "satisfied"
        assert snapshot.evidence_limited is False
        assert snapshot.article_entities_count == 7
        assert snapshot.grounded_entities_count == 7
        assert snapshot.recommended_entities_count == 7

    def test_recommended_entities_count_uses_compliance(self):
        class Compliance:
            passes = True
            recommended_count = 6

        snapshot = build_answer_count_snapshot(
            requested_count=7,
            allowed_candidates=_allowed(7),
            entity_audit=_audit(7, 7),
            query_contract=_fragrance_contract(7),
            draft_candidate_compliance=Compliance(),
        )

        assert snapshot.recommended_entities_count == 6
        assert snapshot.count_status == "failed"
        assert "recommended_entities_count" in (snapshot.failure_reason or "")

    def test_evidence_limited_when_fewer_than_requested(self):
        """requested=7, allowed=3, article=3, grounded=3 → evidence_limited (not 'failed')"""
        snapshot = build_answer_count_snapshot(
            requested_count=7,
            allowed_candidates=_allowed(3),
            entity_audit=_audit(3, 3),
            query_contract=_fragrance_contract(7),
            minimum_publishable_items=3,
        )
        assert snapshot.count_status == "evidence_limited"
        assert snapshot.evidence_limited is True
        assert snapshot.article_entities_count == 3
        assert snapshot.grounded_entities_count == 3
        # Must NOT be "0 vs 7" — must accurately reflect the 3 found
        assert snapshot.article_entities_count != 0

    def test_failed_when_below_minimum(self):
        """requested=7, allowed=1, article=1 → failed"""
        snapshot = build_answer_count_snapshot(
            requested_count=7,
            allowed_candidates=_allowed(1),
            entity_audit=_audit(1, 1),
            query_contract=_fragrance_contract(7),
            minimum_publishable_items=3,
        )
        assert snapshot.count_status == "failed"
        assert snapshot.evidence_limited is True

    def test_no_false_zero_count(self):
        """The regression: snapshot must not report 0 when audit found 3."""
        snapshot = build_answer_count_snapshot(
            requested_count=7,
            allowed_candidates=_allowed(3),
            entity_audit=_audit(3, 3),
            query_contract=_fragrance_contract(7),
            minimum_publishable_items=3,
        )
        assert snapshot.article_entities_count == 3, (
            f"Expected 3, not {snapshot.article_entities_count} — "
            "snapshot must not report 0 when audit found 3"
        )

    def test_allowed_candidates_count_from_ledger(self):
        """allowed_candidates_count must reflect the ledger, not the article."""
        snapshot = build_answer_count_snapshot(
            requested_count=7,
            allowed_candidates=_allowed(3),  # ledger has 3
            entity_audit=_audit(3, 3),
            query_contract=_fragrance_contract(7),
        )
        assert snapshot.allowed_candidates_count == 3
        # Not 7 and not 25 (the old false count)
        assert snapshot.allowed_candidates_count != 7
        assert snapshot.allowed_candidates_count != 25

    def test_satisfied_with_no_requested_count(self):
        contract = build_query_contract(
            "best parfums for summer",
            is_recommendation=True,
            is_financial=False,
            requested_count=None,
        )
        snapshot = build_answer_count_snapshot(
            requested_count=None,
            allowed_candidates=_allowed(5),
            entity_audit=_audit(5, 5),
            query_contract=contract,
            minimum_publishable_items=3,
        )
        assert snapshot.count_status == "satisfied"
        assert snapshot.requested_count is None


# ---------------------------------------------------------------------------
# Regression
# ---------------------------------------------------------------------------


class TestRegressionCountCoherence:
    """Ensure the '7 best parfums' regression produces a coherent snapshot."""

    def test_polluted_25_vs_3_is_coherent(self):
        """
        Regression: candidate ledger said '25 usable' while article had only 3.
        The snapshot must reflect the truth: 3 article recommendations,
        not 25 from the inflated ledger.
        """
        # Ledger has 25 raw mentions but only 3 usable clean ones
        snapshot = build_answer_count_snapshot(
            requested_count=7,
            allowed_candidates=_allowed(3),  # 3 usable from ledger (cleaned)
            entity_audit=_audit(3, 3),  # article has 3
            query_contract=_fragrance_contract(7),
            minimum_publishable_items=3,
        )
        # Snapshot must be evidence_limited (3 of 7), not 0 or 25
        assert snapshot.article_entities_count == 3
        assert snapshot.count_status == "evidence_limited"
        assert snapshot.count_status != "satisfied"
        # Must not say "0 recommendations" like the old final validator
        assert snapshot.article_entities_count > 0
