"""Tests for draft_candidate_compliance module.

Verifies that the compliance checker correctly distinguishes between:
- draft_candidate_compliance_failed (allowed >= requested, model used fewer)
- evidence_limited (allowed < requested)
- passed (correct count, all from allowed candidates)
"""

from __future__ import annotations

from blogagent.tools.draft_candidate_compliance import (
    check_draft_candidate_compliance,
)
from blogagent.workflow.query_contract import build_query_contract


def _fragrance_contract(count: int = 7):
    return build_query_contract(
        f"{count} best parfums for summer",
        is_recommendation=True,
        is_financial=False,
        requested_count=count,
    )


def _allowed(names: list[str]) -> list[dict]:
    return [
        {
            "candidate_id": f"cand{i}",
            "canonical_name": name.lower(),
            "name": name,
            "usable": True,
            "source_quality": "high",
        }
        for i, name in enumerate(names)
    ]


PERFUME_NAMES = [
    "Ouai Melrose Place Eau de Parfum",
    "Dolce & Gabbana Light Blue Eau de Toilette",
    "Maison Margiela Replica Afternoon Delight",
    "Tom Ford Soleil Blanc",
    "Jo Malone London Wood Sage & Sea Salt",
    "Chanel Chance Eau Tendre",
    "Dior Miss Dior Blooming Bouquet",
    "Byredo Sundazed",
    "Valentino Donna Born in Roma",
]


def _make_article_with_recs(names: list[str], with_quick_picks: bool = True) -> str:
    lines = ["# 7 Best Parfums for Summer", ""]
    if with_quick_picks:
        lines += ["## Quick Picks", ""]
        for name in names:
            lines.append(f"- **Best for summer:** {name}")
        lines.append("")
    for name in names:
        lines += [f"## {name}", "", "This is a wonderful fragrance for summer.", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Basic compliance checks
# ---------------------------------------------------------------------------


class TestDraftCandidateComplianceBasic:
    def test_non_recommendation_topic_always_passes(self):
        contract = build_query_contract(
            "why elephants are heavy",
            is_recommendation=False,
            is_financial=False,
            requested_count=None,
        )
        result = check_draft_candidate_compliance(
            article_markdown="# Elephants\n\nThey are large animals.",
            allowed_candidates=[],
            query_contract=contract,
        )
        assert result.passes is True
        assert result.failure_reason is None

    def test_allowed_7_article_7_all_allowed_passes(self):
        contract = _fragrance_contract(7)
        allowed_names = PERFUME_NAMES[:7]
        allowed = _allowed(allowed_names)
        article = _make_article_with_recs(allowed_names)

        result = check_draft_candidate_compliance(
            article_markdown=article,
            allowed_candidates=allowed,
            query_contract=contract,
            minimum_publishable_items=3,
        )
        assert result.passes is True, f"Expected pass, got: {result.failure_reason}"
        assert result.requested_count == 7
        assert result.allowed_count == 7

    def test_structured_recommended_entities_match_by_candidate_id(self):
        contract = _fragrance_contract(7)
        allowed_names = PERFUME_NAMES[:7]
        allowed = _allowed(allowed_names)
        article = _make_article_with_recs(allowed_names)
        draft_output = {
            "recommended_entities": [
                {
                    "candidate_id": f"cand{i}",
                    "name": f"Alias {i}",
                    "section_heading": None,
                    "source_url": None,
                }
                for i in range(7)
            ]
        }

        result = check_draft_candidate_compliance(
            article_markdown=article,
            allowed_candidates=allowed,
            query_contract=contract,
            minimum_publishable_items=3,
            draft_output=draft_output,
        )

        assert result.passes is True
        assert result.recommended_count == 7
        assert result.allowed_recommended_count == 7

    def test_allowed_9_requested_7_article_2_fails(self):
        """Regression test: 9 allowed, 7 requested, but article uses only 2."""
        contract = _fragrance_contract(7)
        allowed = _allowed(PERFUME_NAMES[:9])
        article = _make_article_with_recs(PERFUME_NAMES[:2])

        result = check_draft_candidate_compliance(
            article_markdown=article,
            allowed_candidates=allowed,
            query_contract=contract,
            minimum_publishable_items=3,
        )
        assert result.passes is False
        assert "draft_candidate_compliance_failed" in (result.failure_reason or "")
        assert result.allowed_count == 9
        assert result.recommended_count == 2

    def test_missing_quick_picks_fails(self):
        contract = _fragrance_contract(7)
        allowed = _allowed(PERFUME_NAMES[:7])
        article = _make_article_with_recs(PERFUME_NAMES[:7], with_quick_picks=False)

        result = check_draft_candidate_compliance(
            article_markdown=article,
            allowed_candidates=allowed,
            query_contract=contract,
            minimum_publishable_items=3,
        )
        assert result.passes is False
        assert result.has_quick_picks is False
        fr = result.failure_reason or ""
        assert "Quick Picks" in fr or "quick_picks" in fr


# ---------------------------------------------------------------------------
# Evidence-limited framing
# ---------------------------------------------------------------------------


class TestEvidenceLimitedCompliance:
    def test_allowed_3_article_3_evidence_limited_passes(self):
        """3 allowed for 7 requested + article uses 3 = evidence-limited but passes."""
        contract = _fragrance_contract(7)
        allowed = _allowed(PERFUME_NAMES[:3])
        article = _make_article_with_recs(PERFUME_NAMES[:3])

        result = check_draft_candidate_compliance(
            article_markdown=article,
            allowed_candidates=allowed,
            query_contract=contract,
            minimum_publishable_items=3,
        )
        assert result.passes is True, (
            f"Evidence-limited 3/7 should pass compliance; got: {result.failure_reason}"
        )

    def test_allowed_2_article_2_below_minimum_still_passes_compliance(self):
        """Below minimum candidates — compliance passes (evidence-limited, not draft failure)."""
        contract = _fragrance_contract(7)
        allowed = _allowed(PERFUME_NAMES[:2])
        article = _make_article_with_recs(PERFUME_NAMES[:2])

        result = check_draft_candidate_compliance(
            article_markdown=article,
            allowed_candidates=allowed,
            query_contract=contract,
            minimum_publishable_items=3,
        )
        # Below minimum_publishable_items = compliance still passes (not draft fault)
        assert result.passes is True


# ---------------------------------------------------------------------------
# Unknown recommended entities
# ---------------------------------------------------------------------------


class TestUnknownRecommendedEntities:
    def test_article_uses_non_allowed_entity_fails(self):
        contract = _fragrance_contract(7)
        allowed = _allowed(PERFUME_NAMES[:7])
        # Article uses Creed Aventus which is NOT in the allowed list
        article = _make_article_with_recs(PERFUME_NAMES[:6] + ["Creed Aventus"])

        result = check_draft_candidate_compliance(
            article_markdown=article,
            allowed_candidates=allowed,
            query_contract=contract,
            minimum_publishable_items=3,
        )
        assert result.passes is False
        assert len(result.unknown_recommended_entities) > 0


class TestRecommendedEntityDerivation:
    def test_derives_recommended_entities_from_markdown(self):
        from blogagent.tools.draft_candidate_compliance import (
            derive_recommended_entities_from_markdown,
        )

        allowed = _allowed(PERFUME_NAMES[:3])
        article = _make_article_with_recs(PERFUME_NAMES[:3])

        result = derive_recommended_entities_from_markdown(article, allowed)

        assert [r["candidate_id"] for r in result] == ["cand0", "cand1", "cand2"]
        assert result[0]["name"] == PERFUME_NAMES[0].lower()


# ---------------------------------------------------------------------------
# Revision output completion
# ---------------------------------------------------------------------------


class TestRevisionOutputCompletion:
    def test_revision_with_missing_summary_synthesizes(self):
        """If revised_markdown exists but revision_summary is missing, synthesis should occur."""
        import json

        from blogagent.llm.client import _try_complete_revision_output
        from blogagent.llm.schemas import RevisionOutput
        raw = json.dumps({"revised_markdown": "# Revised\n\nSome content."})
        result, ok = _try_complete_revision_output(raw, RevisionOutput)
        assert ok is True
        assert result is not None
        assert result.revised_markdown == "# Revised\n\nSome content."
        assert "synthesized" in result.revision_summary.lower()

    def test_revision_with_missing_revised_markdown_fails(self):
        """If revised_markdown is absent, completion should fail and return (None, False)."""
        import json

        from blogagent.llm.client import _try_complete_revision_output
        from blogagent.llm.schemas import RevisionOutput
        raw = json.dumps({"revision_summary": "only summary, no markdown"})
        result, ok = _try_complete_revision_output(raw, RevisionOutput)
        assert ok is False
        assert result is None

    def test_complete_revision_output_passes_through(self):
        """Both fields present → parse normally."""
        import json

        from blogagent.llm.client import _try_complete_revision_output
        from blogagent.llm.schemas import RevisionOutput
        raw = json.dumps({
            "revised_markdown": "# Article\n\nContent.",
            "revision_summary": "Fixed the top-N count.",
        })
        result, ok = _try_complete_revision_output(raw, RevisionOutput)
        assert ok is True
        assert result.revision_summary == "Fixed the top-N count."


# ---------------------------------------------------------------------------
# Publish contract hard fail on compliance failure
# ---------------------------------------------------------------------------


class TestPublishContractComplianceFail:
    def test_compliance_failure_triggers_high_severity_defect(self):
        from blogagent.agents.publish_contract import check_publish_contract

        contract = _fragrance_contract(7).model_dump()
        article = _make_article_with_recs(PERFUME_NAMES[:2])  # only 2 of 7
        compliance_dict = {
            "passes": False,
            "requested_count": 7,
            "allowed_count": 9,
            "recommended_count": 2,
            "allowed_recommended_count": 2,
            "has_quick_picks": True,
            "failure_reason": "draft_candidate_compliance_failed: 9 allowed, 2 used",
        }

        result = check_publish_contract(
            article_markdown=article,
            topic="7 best parfums for summer",
            publishability_score=80,
            publishability_defects=[],
            is_recommendation=True,
            requested_count=7,
            evidence_sufficiency=None,
            source_quality_scores=[{"quality": "high"}, {"quality": "high"}],
            query_contract=contract,
            validated_candidates=_allowed(PERFUME_NAMES[:9]),
            draft_candidate_compliance=compliance_dict,
        )
        assert result.passes is False
        assert result.status == "draft_only_not_publish_ready"
        compliance_defects = [
            d for d in result.defects
            if d.type == "draft_candidate_compliance_failed"
        ]
        assert len(compliance_defects) > 0

    def test_evidence_limited_not_accepted_when_allowed_gte_requested(self):
        """allowed=9, requested=7 → should NOT accept evidence-limited framing."""
        from blogagent.agents.publish_contract import check_publish_contract

        contract = _fragrance_contract(7).model_dump()
        article = _make_article_with_recs(PERFUME_NAMES[:2])
        snap = {
            "requested_count": 7,
            "allowed_candidates_count": 9,
            "article_entities_count": 2,
            "grounded_entities_count": 1,
            "evidence_limited": False,
            "count_status": "failed",
            "draft_candidate_compliance_passes": False,
        }

        result = check_publish_contract(
            article_markdown=article,
            topic="7 best parfums for summer",
            publishability_score=80,
            publishability_defects=[],
            is_recommendation=True,
            requested_count=7,
            evidence_sufficiency=None,
            source_quality_scores=[{"quality": "high"}],
            query_contract=contract,
            validated_candidates=_allowed(PERFUME_NAMES[:9]),
            answer_count_snapshot=snap,
        )
        # Should be draft_only, not accept evidence-limited framing
        assert result.status == "draft_only_not_publish_ready"
        # Should NOT have an evidence-limited accepted defect
        ev_limited_accepted = [
            d for d in result.defects
            if "evidence-limited framing accepted" in d.message
        ]
        assert len(ev_limited_accepted) == 0, (
            "Should not accept evidence-limited when allowed >= requested"
        )
