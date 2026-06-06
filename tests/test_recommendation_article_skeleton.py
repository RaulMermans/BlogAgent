from __future__ import annotations

from blogagent.tools.candidate_pack import CandidatePack, CandidatePackItem
from blogagent.tools.recommendation_article_skeleton import (
    build_candidate_locked_recommendation_skeleton,
)
from blogagent.workflow.query_contract import build_query_contract


def _contract():
    return build_query_contract(
        "7 best parfums for summer",
        is_recommendation=True,
        is_financial=False,
        requested_count=7,
    )


def _pack(mode: str = "evidence_limited", count: int = 3):
    items = [
        CandidatePackItem(
            candidate_id=f"c{i}",
            canonical_name=f"Perfume {i}",
            display_name=f"Perfume {i}",
            section_heading=f"Perfume {i}",
            entity_type="specific_product",
        )
        for i in range(1, count + 1)
    ]
    return CandidatePack(
        requested_count=7,
        allowed_count=count,
        final_target_count=count,
        mode=mode,
        minimum_publishable_items=3,
        evidence_limited=mode == "evidence_limited",
        items=items,
        rejected_items=[],
        count_policy="locked",
        locked_candidate_ids=[item.candidate_id for item in items],
        locked_display_names=[item.display_name for item in items],
    )


def test_skeleton_contains_locked_count_quick_picks_and_detail_sections():
    skeleton = build_candidate_locked_recommendation_skeleton(
        _contract(), _pack(), "summer parfums"
    )
    assert skeleton.startswith("# 3 ")
    assert "## Quick Picks" in skeleton
    assert skeleton.count("\n## 1. Perfume 1") == 1
    assert "\n## 2. Perfume 2" in skeleton
    assert "\n## 3. Perfume 3" in skeleton
    assert "validated candidates" not in skeleton.lower()


def test_below_minimum_skeleton_is_evidence_report_not_best_list():
    skeleton = build_candidate_locked_recommendation_skeleton(
        _contract(), _pack("below_minimum", 2), "summer parfums"
    )
    assert skeleton.startswith("# Evidence Report:")
    assert "## Why Not Publish-Ready" in skeleton
    assert "## What Evidence Is Missing" in skeleton
