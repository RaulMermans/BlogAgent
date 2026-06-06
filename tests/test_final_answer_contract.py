"""Tests for FinalAnswerContract — canonical post-polish publish status arbiter.

Tests A-H map directly to the sprint requirements:
  A. Exact count pass
  B. Evidence-limited pass
  C. Current regression (requested=7, allowed=5, article=3)
  D. Impossible state blocker (count_status=failed → never publish_ready_with_warnings)
  E. Title mismatch
  F. Quick Picks mismatch
  G. Candidate ledger dominance
  H. UI / RunResponse contract

Additional tests cover edge cases and publish_contract invariant.
"""

from __future__ import annotations

import pytest

from blogagent.tools.final_answer_contract import (
    FinalAnswerContract,
    _count_detail_sections,
    _count_quick_picks,
    _extract_count_from_title,
    build_final_answer_contract,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _rec_query_contract(requested_count: int | None = None) -> dict:
    return {
        "task_type": "recommendation",
        "domain": "beauty_fragrance",
        "answer_entity_type": "specific_product",
        "entity_subtype": "fragrance_product",
        "minimum_publishable_items": 3,
        "requested_count": requested_count,
    }


def _consumer_query_contract(requested_count: int | None = 5) -> dict:
    return {
        "task_type": "recommendation",
        "domain": "consumer_products",
        "answer_entity_type": "specific_product",
        "entity_subtype": "watch",
        "minimum_publishable_items": 3,
        "requested_count": requested_count,
    }


def _snap(
    *,
    requested: int | None,
    allowed: int,
    article: int,
    grounded: int,
    status: str,
    failure_reason: str | None = None,
    recommended: int | None = None,
) -> dict:
    return {
        "requested_count": requested,
        "allowed_candidates_count": allowed,
        "article_entities_count": article,
        "grounded_entities_count": grounded,
        "recommended_entities_count": recommended if recommended is not None else article,
        "count_status": status,
        "evidence_limited": allowed < (requested or allowed + 1),
        "failure_reason": failure_reason,
    }


def _ledger(usable: int) -> dict:
    return {"usable_count": usable, "table_quality": "limited" if usable > 0 else "failed"}


def _ledger_quality(usable: int, quality: str) -> dict:
    return {"usable_count": usable, "table_quality": quality}


def _article_exact(n: int, name_prefix: str = "Parfum") -> str:
    """Build a well-structured article with exactly n items."""
    title = f"# {n} Best {name_prefix}s for Summer\n\n"
    intro = "A source-backed editorial guide.\n\n"
    qp = "## Quick Picks\n\n" + "".join(
        f"- **Best #{i}:** {name_prefix} {i}\n" for i in range(1, n + 1)
    ) + "\n"
    sections = "".join(
        f"## {i}. {name_prefix} {i}\n\nDetail about {name_prefix} {i}.\n\n"
        for i in range(1, n + 1)
    )
    return title + intro + qp + sections


def _article_with_title_count(article_items: int, title_count: int) -> str:
    """Build an article where the title declares a different count than the body."""
    title = f"# {title_count} Best Parfums for Summer\n\n"
    intro = "A guide.\n\n"
    qp = "## Quick Picks\n\n" + "".join(
        f"- **Best #{i}:** Parfum {i}\n" for i in range(1, article_items + 1)
    ) + "\n"
    sections = "".join(
        f"## {i}. Parfum {i}\n\nDetail.\n\n" for i in range(1, article_items + 1)
    )
    return title + intro + qp + sections


def _article_quick_picks_only(n: int) -> str:
    """Article with n items in Quick Picks and no numbered sections."""
    title = f"# {n} Best Parfums\n\n"
    qp = "## Quick Picks\n\n" + "".join(
        f"- **Best #{i}:** Parfum {i}\n" for i in range(1, n + 1)
    ) + "\n"
    return title + qp + "## Conclusion\nGreat picks.\n"


def _build(**kwargs) -> FinalAnswerContract:
    """Convenience wrapper for build_final_answer_contract."""
    defaults = dict(
        article_markdown="",
        title="",
        meta_description="",
        answer_count_snapshot=None,
        candidate_ledger_summary=None,
        query_contract=_rec_query_contract(),
        publish_contract=None,
        minimum_publishable_items=3,
        is_recommendation=True,
    )
    defaults.update(kwargs)
    return build_final_answer_contract(**defaults)


# ---------------------------------------------------------------------------
# A. Exact count pass
# ---------------------------------------------------------------------------


class TestExactCountPass:
    """A. Exact mode: requested=5, allowed=5, article=5, grounded=5, qp=5 → publish_ready."""

    def test_publish_ready(self):
        n = 5
        fac = _build(
            article_markdown=_article_exact(n),
            title=f"{n} Best Parfums for Summer",
            answer_count_snapshot=_snap(
                requested=n, allowed=n, article=n, grounded=n, status="satisfied"
            ),
            candidate_ledger_summary=_ledger(n),
        )
        assert fac.publish_status == "publish_ready"
        assert fac.final_count_mode == "exact"
        assert fac.failure_reasons == []

    def test_counts_accurate(self):
        n = 5
        fac = _build(
            article_markdown=_article_exact(n),
            title=f"{n} Best Parfums for Summer",
            answer_count_snapshot=_snap(
                requested=n, allowed=n, article=n, grounded=n, status="satisfied"
            ),
            candidate_ledger_summary=_ledger(n),
        )
        assert fac.requested_count == n
        assert fac.allowed_count == n
        assert fac.final_article_count == n
        assert fac.grounded_count == n
        assert fac.quick_picks_count == n
        assert fac.detail_sections_count == n
        assert fac.title_declared_count == n

    def test_three_items_exact(self):
        """Minimum publishable count with exact match."""
        n = 3
        fac = _build(
            article_markdown=_article_exact(n),
            title=f"{n} Best Fragrances",
            answer_count_snapshot=_snap(
                requested=n, allowed=n, article=n, grounded=n, status="satisfied"
            ),
            candidate_ledger_summary=_ledger(n),
        )
        assert fac.publish_status == "publish_ready"
        assert fac.final_count_mode == "exact"

    def test_consumer_products_exact_publish_ready(self):
        n = 5
        fac = _build(
            article_markdown=_article_exact(n, name_prefix="Watch"),
            title="5 Best Watches for Everyday Wear",
            answer_count_snapshot=_snap(
                requested=n, allowed=n, article=n, grounded=n, status="satisfied"
            ),
            candidate_ledger_summary=_ledger_quality(n, "strong"),
            query_contract=_consumer_query_contract(n),
        )
        assert fac.publish_status == "publish_ready"
        assert fac.final_count_mode == "exact"


# ---------------------------------------------------------------------------
# B. Evidence-limited pass
# ---------------------------------------------------------------------------


class TestEvidenceLimitedPass:
    """B. Evidence-limited: requested=7, allowed=5, article=5 → publish_ready_with_warnings."""

    def test_publish_ready_with_warnings(self):
        fac = _build(
            article_markdown=_article_exact(5),
            title="5 Best Parfums for Summer",
            answer_count_snapshot=_snap(
                requested=7, allowed=5, article=5, grounded=5, status="evidence_limited"
            ),
            candidate_ledger_summary=_ledger(5),
        )
        assert fac.publish_status == "publish_ready_with_editorial_review"
        assert fac.final_count_mode == "evidence_limited"
        assert fac.failure_reasons == []
        assert len(fac.warning_reasons) >= 1

    def test_warning_mentions_counts(self):
        fac = _build(
            article_markdown=_article_exact(5),
            title="5 Best Parfums for Summer",
            answer_count_snapshot=_snap(
                requested=7, allowed=5, article=5, grounded=5, status="evidence_limited"
            ),
            candidate_ledger_summary=_ledger(5),
        )
        combined = " ".join(fac.warning_reasons).lower()
        assert "5" in combined  # final count
        assert "7" in combined  # requested count

    def test_evidence_limited_counts_accurate(self):
        fac = _build(
            article_markdown=_article_exact(5),
            title="5 Best Parfums for Summer",
            answer_count_snapshot=_snap(
                requested=7, allowed=5, article=5, grounded=5, status="evidence_limited"
            ),
            candidate_ledger_summary=_ledger(5),
        )
        assert fac.requested_count == 7
        assert fac.allowed_count == 5
        assert fac.final_article_count == 5
        assert fac.grounded_count == 5
        assert fac.quick_picks_count == 5

    def test_consumer_products_evidence_limited_publish_ready_with_warnings(self):
        fac = _build(
            article_markdown=_article_exact(3, name_prefix="Watch"),
            title="3 Best Watches for Everyday Wear",
            answer_count_snapshot=_snap(
                requested=5, allowed=3, article=3, grounded=3, status="evidence_limited"
            ),
            candidate_ledger_summary=_ledger_quality(3, "limited"),
            query_contract=_consumer_query_contract(5),
        )
        assert fac.publish_status == "publish_ready_with_editorial_review"
        assert fac.final_count_mode == "evidence_limited"


# ---------------------------------------------------------------------------
# C. Current regression — requested=7, allowed=5, article=3
# ---------------------------------------------------------------------------


class TestRegressionCase:
    """C. requested=7, allowed=5, article=3, grounded=3 → draft_only_not_publish_ready."""

    def test_draft_only(self):
        fac = _build(
            article_markdown=_article_exact(3),
            title="3 Best Parfums",
            answer_count_snapshot=_snap(
                requested=7,
                allowed=5,
                article=3,
                grounded=3,
                status="failed",
                failure_reason="evidence-limited count mismatch: article=3, allowed=5",
            ),
            candidate_ledger_summary=_ledger(5),
        )
        assert fac.publish_status == "draft_only_not_publish_ready"
        assert fac.final_count_mode == "failed"
        assert len(fac.failure_reasons) >= 1

    def test_failure_reason_mentions_shortfall(self):
        fac = _build(
            article_markdown=_article_exact(3),
            title="3 Best Parfums",
            answer_count_snapshot=_snap(
                requested=7,
                allowed=5,
                article=3,
                grounded=3,
                status="failed",
                failure_reason="evidence-limited count mismatch: article=3, allowed=5",
            ),
            candidate_ledger_summary=_ledger(5),
        )
        combined = " ".join(fac.failure_reasons).lower()
        # Should mention that fewer items were used than allowed
        assert "3" in combined
        assert "5" in combined or "allowed" in combined

    def test_correct_counts_stored(self):
        fac = _build(
            article_markdown=_article_exact(3),
            title="3 Best Parfums",
            answer_count_snapshot=_snap(
                requested=7, allowed=5, article=3, grounded=3, status="failed"
            ),
            candidate_ledger_summary=_ledger(5),
        )
        assert fac.requested_count == 7
        assert fac.allowed_count == 5
        assert fac.final_article_count == 3
        assert fac.grounded_count == 3

    def test_consumer_products_requested_five_allowed_five_article_three_fails(self):
        fac = _build(
            article_markdown=_article_exact(3, name_prefix="Watch"),
            title="3 Best Watches",
            answer_count_snapshot=_snap(
                requested=5,
                allowed=5,
                article=3,
                grounded=3,
                status="failed",
                failure_reason="draft_candidate_compliance_failed: used 3/5",
            ),
            candidate_ledger_summary=_ledger_quality(5, "strong"),
            query_contract=_consumer_query_contract(5),
        )
        assert fac.publish_status == "draft_only_not_publish_ready"
        assert fac.final_count_mode == "failed"

    def test_consumer_products_candidate_ledger_not_required_fails(self):
        fac = _build(
            article_markdown=_article_exact(5, name_prefix="Watch"),
            title="5 Best Watches",
            answer_count_snapshot=_snap(
                requested=5, allowed=0, article=5, grounded=5, status="not_applicable"
            ),
            candidate_ledger_summary=_ledger_quality(0, "not_required"),
            query_contract=_consumer_query_contract(5),
        )
        assert fac.publish_status == "draft_only_not_publish_ready"
        assert fac.final_count_mode == "failed"
        assert any("not_required" in r for r in fac.failure_reasons)


# ---------------------------------------------------------------------------
# D. Impossible state blocker — count_status=failed cannot produce publish_ready_with_warnings
# ---------------------------------------------------------------------------


class TestImpossibleStateBlocker:
    """D. answer_count_snapshot.count_status=failed → never publish_ready_with_warnings."""

    @pytest.mark.parametrize(
        "requested,allowed,article,grounded",
        [
            (7, 5, 3, 3),  # regression case
            (5, 5, 2, 2),  # compliance failure (had enough candidates, used fewer)
            (7, 0, 7, 7),  # impossible: allowed=0 but article=7
            (3, 3, 0, 0),  # no recommendations at all
        ],
    )
    def test_failed_snapshot_never_publish_ready_with_warnings(
        self, requested, allowed, article, grounded
    ):
        fac = _build(
            article_markdown=_article_exact(max(article, 0)),
            title=f"{article} Best",
            answer_count_snapshot=_snap(
                requested=requested,
                allowed=allowed,
                article=article,
                grounded=grounded,
                status="failed",
            ),
            candidate_ledger_summary=_ledger(allowed),
        )
        assert fac.publish_status != "publish_ready_with_warnings", (
            f"count_status=failed must not produce publish_ready_with_warnings: "
            f"got {fac.publish_status!r} (requested={requested}, allowed={allowed}, "
            f"article={article})"
        )

    def test_failed_status_with_evidence_limited_explanation_still_fails(self):
        """Even if the article body has evidence-limited wording, count_status=failed wins."""
        article = (
            "# 3 Best Parfums\n\n"
            "## Quick Picks\n\n- A\n- B\n- C\n\n"
            "## 1. A\nDetail.\n## 2. B\nDetail.\n## 3. C\nDetail.\n\n"
            "Note: available evidence supported only 3 of 7 requested items.\n"
        )
        fac = _build(
            article_markdown=article,
            title="3 Best Parfums",
            answer_count_snapshot=_snap(
                requested=7, allowed=5, article=3, grounded=3, status="failed",
                failure_reason="evidence-limited count mismatch: article=3, allowed=5",
            ),
            candidate_ledger_summary=_ledger(5),
        )
        assert fac.publish_status == "draft_only_not_publish_ready"
        assert fac.final_count_mode == "failed"


# ---------------------------------------------------------------------------
# E. Title mismatch
# ---------------------------------------------------------------------------


class TestTitleMismatch:
    """E. requested=7, allowed=5, article=5, title says '7 Best' → draft_only."""

    def test_title_declares_requested_count_when_evidence_limited(self):
        """Title says 7 but article has 5 (evidence-limited) → draft_only."""
        fac = _build(
            article_markdown=_article_with_title_count(article_items=5, title_count=7),
            title="7 Best Parfums for Summer",
            answer_count_snapshot=_snap(
                requested=7, allowed=5, article=5, grounded=5, status="evidence_limited"
            ),
            candidate_ledger_summary=_ledger(5),
        )
        assert fac.publish_status == "draft_only_not_publish_ready"
        assert fac.title_declared_count == 7
        assert any("title" in r.lower() or "7" in r for r in fac.failure_reasons)

    def test_title_matches_article_count_passes(self):
        """Title says 5, article has 5 → evidence-limited passes."""
        fac = _build(
            article_markdown=_article_with_title_count(article_items=5, title_count=5),
            title="5 Best Parfums for Summer",
            answer_count_snapshot=_snap(
                requested=7, allowed=5, article=5, grounded=5, status="evidence_limited"
            ),
            candidate_ledger_summary=_ledger(5),
        )
        assert fac.publish_status == "publish_ready_with_editorial_review"
        assert fac.title_declared_count == 5
        assert fac.failure_reasons == []

    def test_exact_mode_title_mismatch(self):
        """Title says 7 but article has 5 with allowed=5, requested=5 → fails."""
        fac = _build(
            article_markdown=_article_with_title_count(article_items=5, title_count=7),
            title="7 Best Fragrances",
            answer_count_snapshot=_snap(
                requested=5, allowed=5, article=5, grounded=5, status="satisfied"
            ),
            candidate_ledger_summary=_ledger(5),
        )
        assert fac.publish_status == "draft_only_not_publish_ready"
        assert fac.title_declared_count == 7

    def test_no_title_count_passes(self):
        """Title with no number → title_declared_count=None → no title failure."""
        _untitled = (
            "# Best Summer Parfums\n\n"
            "## Quick Picks\n\n- A\n- B\n- C\n- D\n- E\n\n"
            "## 1. A\nD.\n## 2. B\nD.\n## 3. C\nD.\n## 4. D\nD.\n## 5. E\nD.\n"
        )
        fac = _build(
            article_markdown=_untitled,
            title="Best Summer Parfums",
            answer_count_snapshot=_snap(
                requested=5, allowed=5, article=5, grounded=5, status="satisfied"
            ),
            candidate_ledger_summary=_ledger(5),
        )
        assert fac.title_declared_count is None
        assert fac.publish_status == "publish_ready"


# ---------------------------------------------------------------------------
# F. Quick Picks mismatch
# ---------------------------------------------------------------------------


class TestQuickPicksMismatch:
    """F. 5 detail sections but 3 Quick Picks → draft_only_not_publish_ready."""

    def _article_qp_detail_mismatch(self, qp_count: int, section_count: int) -> str:
        title = f"# {section_count} Best Parfums\n\n"
        qp = "## Quick Picks\n\n" + "".join(
            f"- **Best #{i}:** Parfum {i}\n" for i in range(1, qp_count + 1)
        ) + "\n"
        sections = "".join(
            f"## {i}. Parfum {i}\n\nDetail.\n\n" for i in range(1, section_count + 1)
        )
        return title + qp + sections

    def test_qp_less_than_detail_sections(self):
        """Quick Picks=3, detail sections=5 → draft_only."""
        fac = _build(
            article_markdown=self._article_qp_detail_mismatch(qp_count=3, section_count=5),
            title="5 Best Parfums",
            # Entity audit sees 5 from sections; snapshot reports 5
            answer_count_snapshot=_snap(
                requested=5, allowed=5, article=5, grounded=5, status="satisfied"
            ),
            candidate_ledger_summary=_ledger(5),
        )
        assert fac.publish_status == "draft_only_not_publish_ready"
        assert fac.quick_picks_count == 3
        assert fac.detail_sections_count == 5
        assert any("quick picks" in r.lower() or "3" in r for r in fac.failure_reasons)

    def test_matching_qp_and_sections_passes(self):
        """Quick Picks=5, detail sections=5 → passes (no structural mismatch)."""
        fac = _build(
            article_markdown=_article_exact(5),
            title="5 Best Parfums",
            answer_count_snapshot=_snap(
                requested=5, allowed=5, article=5, grounded=5, status="satisfied"
            ),
            candidate_ledger_summary=_ledger(5),
        )
        assert fac.quick_picks_count == 5
        assert fac.detail_sections_count == 5
        assert fac.publish_status == "publish_ready"

    def test_missing_quick_picks_entirely(self):
        """No Quick Picks section at all → draft_only."""
        article = (
            "# 5 Best Parfums\n\nIntro.\n\n"
            "## 1. A\nDetail.\n## 2. B\nDetail.\n## 3. C\nDetail.\n"
            "## 4. D\nDetail.\n## 5. E\nDetail.\n"
        )
        fac = _build(
            article_markdown=article,
            title="5 Best Parfums",
            answer_count_snapshot=_snap(
                requested=5, allowed=5, article=5, grounded=5, status="satisfied"
            ),
            candidate_ledger_summary=_ledger(5),
        )
        assert fac.quick_picks_count == 0
        assert fac.publish_status == "draft_only_not_publish_ready"
        assert any("quick picks" in r.lower() for r in fac.failure_reasons)


# ---------------------------------------------------------------------------
# G. Candidate ledger dominance
# ---------------------------------------------------------------------------


class TestCandidateLedgerDominance:
    """G. recommendation_candidates_summary.usable_count=11 but ledger.allowed_count=5 → use 5."""

    def test_ledger_count_dominates_broader_extraction(self):
        """allowed_count must come from ledger (5), not the broader extraction (11)."""
        fac = _build(
            article_markdown=_article_exact(5),
            title="5 Best Parfums",
            answer_count_snapshot=_snap(
                requested=7, allowed=5, article=5, grounded=5, status="evidence_limited"
            ),
            candidate_ledger_summary=_ledger(5),  # authoritative: 5
            # recommendation_candidates_summary is NOT passed; would claim 11
        )
        assert fac.allowed_count == 5, (
            f"allowed_count must be 5 (from ledger), got {fac.allowed_count}"
        )

    def test_ledger_takes_precedence_over_snapshot_when_different(self):
        """If ledger has 5 but snapshot (via old candidates) has 11, ledger wins."""
        snap_with_inflated_count = _snap(
            requested=7,
            allowed=11,  # inflated by broad extraction
            article=5,
            grounded=5,
            status="evidence_limited",
        )
        fac = _build(
            article_markdown=_article_exact(5),
            title="5 Best Parfums",
            answer_count_snapshot=snap_with_inflated_count,
            candidate_ledger_summary=_ledger(5),  # ledger says 5 — this wins
        )
        assert fac.allowed_count == 5

    def test_no_ledger_falls_back_to_snapshot(self):
        """Without ledger summary, falls back to snapshot's allowed_candidates_count."""
        fac = _build(
            article_markdown=_article_exact(5),
            title="5 Best Parfums",
            answer_count_snapshot=_snap(
                requested=7, allowed=5, article=5, grounded=5, status="evidence_limited"
            ),
            candidate_ledger_summary=None,  # no ledger — use snapshot
        )
        assert fac.allowed_count == 5


# ---------------------------------------------------------------------------
# H. UI — RunResponse includes final_answer_contract
# ---------------------------------------------------------------------------


class TestRunResponseContract:
    """H. final_answer_contract is present in RunResponse schema."""

    def test_run_response_has_final_answer_contract_field(self):
        """RunResponse must expose final_answer_contract as a field."""
        from api.index import RunResponse  # noqa: PLC0415

        fields = RunResponse.model_fields
        assert "final_answer_contract" in fields, (
            "RunResponse must have a final_answer_contract field"
        )

    def test_run_response_default_is_empty_dict(self):
        """Default value for final_answer_contract must be an empty dict."""
        from api.index import RunResponse  # noqa: PLC0415

        # Minimal valid RunResponse
        resp = RunResponse(
            blocked=False,
            block_reason="",
            execution_mode="mock",
            title="T",
            slug="t",
            meta_description="",
            seo_keywords=[],
            article_markdown="",
            source_count=0,
            claim_status_counts={"supported": 0, "partially_supported": 0, "unsupported": 0},
            revision_count=0,
            warnings=[],
            provider_events=[],
        )
        assert resp.final_answer_contract == {}


# ---------------------------------------------------------------------------
# publish_contract.py invariant — count_status=failed enforced at contract level too
# ---------------------------------------------------------------------------


class TestPublishContractInvariant:
    """Hard invariant: count_status=failed cannot yield publish_ready_with_warnings."""

    def test_count_status_failed_forces_draft_only(self):
        from blogagent.agents.publish_contract import check_publish_contract  # noqa: PLC0415

        # Scenario: score is high, no other defects, but count_status=failed
        result = check_publish_contract(
            article_markdown=(
                "# 3 Best Parfums\n\n## Quick Picks\n\n- A\n- B\n- C\n\n"
                "## 1. A\nDetail.\n## 2. B\nDetail.\n## 3. C\nDetail.\n"
                "Note: available evidence supported only 3 of 7 items.\n"
            ),
            topic="best parfums for summer",
            publishability_score=80,
            publishability_defects=[],
            is_recommendation=True,
            requested_count=7,
            evidence_sufficiency=None,
            source_quality_scores=[{"quality": "high"}, {"quality": "high"}],
            answer_count_snapshot={
                "requested_count": 7,
                "allowed_candidates_count": 5,
                "article_entities_count": 3,
                "grounded_entities_count": 3,
                "count_status": "failed",
                "evidence_limited": True,
                "failure_reason": "evidence-limited count mismatch: article=3, allowed=5",
            },
        )
        assert result.status != "publish_ready_with_warnings", (
            f"count_status=failed must not produce publish_ready_with_warnings; "
            f"got {result.status!r}"
        )
        assert result.status == "draft_only_not_publish_ready"
        assert result.passes is False

    def test_count_status_failed_adds_defect(self):
        from blogagent.agents.publish_contract import check_publish_contract  # noqa: PLC0415

        result = check_publish_contract(
            article_markdown="# 3 Best\n\n## Quick Picks\n\n- A\n- B\n- C\n\n",
            topic="best parfums",
            publishability_score=85,
            publishability_defects=[],
            is_recommendation=True,
            requested_count=7,
            evidence_sufficiency=None,
            source_quality_scores=[],
            answer_count_snapshot={
                "count_status": "failed",
                "allowed_candidates_count": 5,
                "article_entities_count": 3,
                "failure_reason": "article used 3 of 5 allowed",
            },
        )
        defect_types = [d.type for d in result.defects]
        assert "count_status_failed" in defect_types, (
            f"Expected count_status_failed defect; got defects: {defect_types}"
        )


# ---------------------------------------------------------------------------
# Non-recommendation / not_applicable path
# ---------------------------------------------------------------------------


class TestNotApplicablePath:
    """Non-recommendation topics → not_applicable mode, defers to publish_contract."""

    def test_explainer_topic_not_applicable(self):
        fac = build_final_answer_contract(
            article_markdown="# Why Elephants Are Large\n\nFactual content.\n",
            title="Why Elephants Are Large",
            meta_description="",
            answer_count_snapshot=None,
            candidate_ledger_summary=None,
            query_contract={
                "task_type": "explainer",
                "answer_entity_type": "general_answer",
                "minimum_publishable_items": 1,
            },
            publish_contract={"status": "publish_ready", "passes": True},
            minimum_publishable_items=1,
            is_recommendation=False,
        )
        assert fac.final_count_mode == "not_applicable"
        assert fac.publish_status == "publish_ready"
        assert fac.failure_reasons == []

    def test_not_applicable_defers_to_draft_only_contract(self):
        fac = build_final_answer_contract(
            article_markdown="# Short article\n\nContent.\n",
            title="Short article",
            meta_description="",
            answer_count_snapshot=None,
            candidate_ledger_summary=None,
            query_contract={"task_type": "explainer", "answer_entity_type": "general_answer"},
            publish_contract={"status": "draft_only_not_publish_ready", "passes": False},
            minimum_publishable_items=1,
            is_recommendation=False,
        )
        assert fac.final_count_mode == "not_applicable"
        assert fac.publish_status == "draft_only_not_publish_ready"


# ---------------------------------------------------------------------------
# Helper function unit tests
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_count_quick_picks_bullets(self):
        md = "# T\n\n## Quick Picks\n\n- **Best:** A\n- **Value:** B\n- **Compact:** C\n\n## 1. A\n"
        assert _count_quick_picks(md) == 3

    def test_count_quick_picks_numbered(self):
        md = "# T\n\n## Quick Picks\n\n1. A\n2. B\n\n## 1. A\n"
        assert _count_quick_picks(md) == 2

    def test_count_quick_picks_none(self):
        assert _count_quick_picks("# T\n\nNo quick picks section.\n") == 0

    def test_count_detail_sections(self):
        md = "# T\n\n## 1. A\n\n## 2. B\n\n## 3. C\n\n## Conclusion\n"
        assert _count_detail_sections(md) == 3

    def test_count_detail_sections_none(self):
        md = "# T\n\n## Introduction\n\n## Conclusion\n"
        assert _count_detail_sections(md) == 0

    def test_extract_count_from_title_n_best(self):
        assert _extract_count_from_title("7 Best Parfums for Summer") == 7

    def test_extract_count_from_title_top_n(self):
        assert _extract_count_from_title("Top 5 Affordable Watches") == 5

    def test_extract_count_from_title_best_n(self):
        assert _extract_count_from_title("Best 3 AI Tools") == 3

    def test_extract_count_from_title_none(self):
        assert _extract_count_from_title("Best Summer Parfums") is None

    def test_extract_count_from_title_year_ignored(self):
        # "2026" should not be extracted as a count
        result = _extract_count_from_title("Best Energy Stocks to Watch in 2026")
        assert result is None or result < 50  # 2026 would be > 50, so rejected by bounds check

    def test_extract_count_bounds_rejected(self):
        # 51 is above the 50 cap
        assert _extract_count_from_title("51 Best Products") is None

    def test_extract_count_single_digit(self):
        assert _extract_count_from_title("3 Best Carry-On Bags") == 3
