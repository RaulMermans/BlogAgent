from __future__ import annotations

from blogagent.tools.candidate_pack import CandidatePack, CandidatePackItem
from blogagent.tools.final_answer_contract import build_final_answer_contract
from blogagent.tools.handoff_auditor import audit_writer_output
from blogagent.tools.locked_entity_repair import repair_locked_recommendation_article
from blogagent.workflow.query_contract import build_query_contract


def _contract():
    return build_query_contract(
        "7 best parfums for summer",
        is_recommendation=True,
        is_financial=False,
        requested_count=7,
    )


def _pack(count: int = 6, mode: str = "evidence_limited") -> CandidatePack:
    items = [
        CandidatePackItem(
            candidate_id=f"c{i}",
            canonical_name=f"Perfume {i}",
            display_name=f"Perfume {i}",
            section_heading=f"Perfume {i}",
            source_url=f"https://example.com/{i}",
            source_title=f"Source {i}",
            source_quality="high",
            source_type="editorial",
            evidence_spans=[f"Perfume {i} has source-backed summer context."],
            evidence_terms=["citrus"],
            supported_context=["summer"],
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


def test_repair_restores_six_from_collapsed_two_item_article():
    pack = _pack()
    article = (
        "# 7 Best Parfums for Summer\n\n"
        "## Quick Picks\n\n- Perfume 1\n- Perfume 2\n\n"
        "## 1. Perfume 1\n\nDetail.\n\n## 2. Perfume 2\n\nDetail.\n\n"
        "## Final Takeaway\n\nTwo picks."
    )
    result = repair_locked_recommendation_article(article, pack, _contract())
    audit = audit_writer_output(result.repaired_markdown, None, pack, _contract())
    assert result.repair_applied is True
    assert audit.quick_picks_count == 6
    assert audit.detail_sections_count == 6
    assert audit.declared_count == 6
    assert audit.missing_candidate_ids == []
    assert len(result.restored_candidate_ids) >= 4


def test_repair_inserts_missing_quick_picks_and_preserves_urls():
    pack = _pack(3)
    article = "# Best Summer Perfumes\n\n## Final Takeaway\n\nDraft."
    result = repair_locked_recommendation_article(article, pack, _contract())
    assert "## Quick Picks" in result.repaired_markdown
    for item in pack.items:
        assert item.source_url in result.repaired_markdown


def test_repair_rewrites_h1_to_final_target_count():
    pack = _pack(6)
    result = repair_locked_recommendation_article(
        "# 7 Best Perfumes\n\n## Quick Picks\n\n- Perfume 1",
        pack,
        _contract(),
    )
    assert result.repaired_markdown.startswith("# 6 ")


def test_below_minimum_stays_draft_only_evidence_report():
    pack = _pack(2, mode="below_minimum")
    result = repair_locked_recommendation_article(
        "# 7 Best Perfumes\n\nA normal best-of article.",
        pack,
        _contract(),
    )
    assert "Evidence Report" in result.repaired_markdown
    assert "Not Publish-Ready" in result.repaired_markdown
    assert "minimum publishable count" in result.repaired_markdown


def _final_contract(article: str, allowed: int, article_count: int, status: str):
    title = article.splitlines()[0].removeprefix("# ").strip()
    return build_final_answer_contract(
        article_markdown=article,
        title=title,
        meta_description="",
        answer_count_snapshot={
            "requested_count": 7,
            "allowed_candidates_count": allowed,
            "recommended_entities_count": article_count,
            "article_entities_count": article_count,
            "grounded_entities_count": article_count,
            "count_status": status,
        },
        candidate_ledger_summary={
            "usable_count": allowed,
            "table_quality": "limited" if allowed >= 3 else "failed",
        },
        query_contract=_contract().model_dump(),
        publish_contract={"status": "publish_ready_with_warnings"},
        minimum_publishable_items=3,
        is_recommendation=True,
    )


def test_final_contract_accepts_repaired_six_of_seven_with_warning():
    pack = _pack(6)
    collapsed = (
        "# 7 Best Parfums\n\n## Quick Picks\n\n- Perfume 1\n- Perfume 2\n\n"
        "## 1. Perfume 1\n\nDetail.\n\n## 2. Perfume 2\n\nDetail."
    )
    repaired = repair_locked_recommendation_article(collapsed, pack, _contract())
    contract = _final_contract(repaired.repaired_markdown, 6, 6, "evidence_limited")
    assert contract.publish_status == "publish_ready_with_editorial_review"
    assert contract.final_article_count == contract.quick_picks_count == 6
    assert contract.detail_sections_count == 6


def test_final_contract_blocks_unrepaired_two_of_six():
    article = (
        "# 2 Source-Backed Picks\n\n## Quick Picks\n\n- Perfume 1\n- Perfume 2\n\n"
        "## 1. Perfume 1\n\nDetail.\n\n## 2. Perfume 2\n\nDetail."
    )
    contract = _final_contract(article, 6, 2, "failed")
    assert contract.publish_status == "draft_only_not_publish_ready"


def test_final_contract_blocks_below_minimum_pack():
    pack = _pack(2, mode="below_minimum")
    repaired = repair_locked_recommendation_article("# 7 Best Parfums", pack, _contract())
    contract = _final_contract(repaired.repaired_markdown, 2, 0, "failed")
    assert contract.publish_status == "draft_only_not_publish_ready"


def test_revision_repairs_extra_recommendation_section():
    """An article with all locked candidates PLUS an extra, unlocked recommendation
    section must have that extra section removed by repair."""
    pack = _pack(3)
    article = (
        "# 3 Recommended Options for Parfums for Summer\n\n"
        "The available evidence supported 3 validated options, rather than the 7 "
        "originally requested.\n\n"
        "## Quick Picks\n\n- Perfume 1\n- Perfume 2\n- Perfume 3\n\n"
        "## 1. Perfume 1\n\nDetail for Perfume 1.\n\n"
        "## 2. Perfume 2\n\nDetail for Perfume 2.\n\n"
        "## 3. Perfume 3\n\nDetail for Perfume 3.\n\n"
        "## 4. Mystery Watch X\n\n"
        "This recommendation was never in the locked candidate table.\n\n"
        "## Final Takeaway\n\nTakeaway."
    )
    result = repair_locked_recommendation_article(article, pack, _contract())
    assert result.repair_applied is True
    assert "Mystery Watch X" not in result.repaired_markdown
    assert "## Final Takeaway" in result.repaired_markdown

    audit = audit_writer_output(result.repaired_markdown, None, pack, _contract())
    assert audit.detail_sections_count == 3
    assert audit.passes_locked_structure is True
