from __future__ import annotations

from api.index import _build_app_html
from blogagent.tools.candidate_pack import build_candidate_pack
from blogagent.tools.entity_candidate_ledger import CandidateLedger, EntityCandidate
from blogagent.tools.final_answer_contract import build_final_answer_contract
from blogagent.tools.recommendation_article_skeleton import (
    build_candidate_locked_recommendation_skeleton,
)
from blogagent.workflow.query_contract import build_query_contract


def _contract(topic: str, count: int | None, *, financial: bool = False):
    return build_query_contract(
        topic,
        is_recommendation=True,
        is_financial=financial,
        requested_count=count,
    )


def _candidate(name: str, index: int, *, confidence: str = "high") -> EntityCandidate:
    return EntityCandidate(
        candidate_id=f"candidate-{index}",
        raw_mention=name,
        canonical_name=name,
        name=name,
        entity_type="specific_product",
        entity_subtype="fragrance_product",
        domain="beauty_fragrance",
        source_urls=[f"https://example.com/{index}"],
        source_titles=["Summer fragrance picks"],
        source_quality="high",
        source_type="editorial",
        evidence_spans=[f"{name} is included in the fragrance list."],
        evidence_terms=["summer"],
        supported_context=["warm weather"],
        clean_name_score=0.95,
        evidence_score=0.9,
        candidate_confidence=confidence,
        candidate_basis="source_exact",
        usable=True,
    )


def _ledger(candidates: list[EntityCandidate], requested: int) -> CandidateLedger:
    return CandidateLedger(
        requested_count=requested,
        raw_mentions_count=len(candidates),
        candidates=candidates,
        validated_candidates=candidates,
        allowed_candidates=candidates,
        rejected_candidates=[],
        usable_count=len(candidates),
        usable_names=[candidate.canonical_name for candidate in candidates],
        rejected_count=0,
        rejected_examples=[],
        table_quality="strong",
        quality_issues=[],
    )


def _article(count: int, title_count: int | None = None) -> str:
    declared = title_count if title_count is not None else count
    quick = "\n".join(f"- Fragrance {index}" for index in range(1, count + 1))
    details = "\n\n".join(
        f"## {index}. Fragrance {index}\n\n**Best for:** Summer\n\nWhy we like it."
        for index in range(1, count + 1)
    )
    return (
        f"# {declared} Best Fragrances for Summer\n\n"
        "A useful edit of warm-weather standouts.\n\n"
        f"## Quick Picks\n\n{quick}\n\n"
        "## How We Chose\n\nWe prioritized distinct use cases and clean identities.\n\n"
        f"{details}\n\n## Final Takeaway\n\nChoose the one that fits your style."
    )


def _final(
    *,
    contract,
    article_count: int,
    grounded_count: int,
    requested_count: int,
    title_count: int | None = None,
    recommendation_audit: dict | None = None,
):
    article = _article(article_count, title_count)
    return build_final_answer_contract(
        article_markdown=article,
        title=article.splitlines()[0].removeprefix("# "),
        meta_description="",
        answer_count_snapshot={
            "requested_count": requested_count,
            "allowed_candidates_count": article_count,
            "recommended_entities_count": article_count,
            "article_entities_count": article_count,
            "grounded_entities_count": grounded_count,
            "count_status": "satisfied",
        },
        candidate_ledger_summary={
            "usable_count": article_count,
            "table_quality": "strong",
        },
        query_contract=contract.model_dump(),
        publish_contract={"status": "publish_ready", "defects": []},
        minimum_publishable_items=3,
        is_recommendation=True,
        recommendation_audit=recommendation_audit,
    )


def test_policy_routes_editorial_standard_and_strict_domains():
    fragrance = _contract("7 best perfumes for summer", 7)
    watches = _contract("5 best affordable luxury watches", 5)
    software = _contract("best AI tools for students", None)
    finance = _contract("best energy stocks to watch in 2026", None, financial=True)

    assert (fragrance.domain, fragrance.recommendation_strictness, fragrance.evidence_mode) == (
        "beauty_fragrance",
        "editorial",
        "source_aware",
    )
    assert (watches.domain, watches.recommendation_strictness, watches.evidence_mode) == (
        "consumer_products",
        "editorial",
        "source_aware",
    )
    assert software.recommendation_strictness == "standard"
    assert finance.recommendation_strictness == "strict"
    assert finance.evidence_mode == "source_required"


def test_editorial_partial_grounding_is_ready_with_review():
    result = _final(
        contract=_contract("7 best perfumes for summer", 7),
        article_count=7,
        grounded_count=4,
        requested_count=7,
    )
    assert result.publish_status == "publish_ready_with_editorial_review"
    assert result.failure_reasons == []
    assert any("source coverage" in reason for reason in result.warning_reasons)


def test_finance_partial_grounding_hard_fails():
    result = _final(
        contract=_contract("5 energy stocks to watch in 2026", 5, financial=True),
        article_count=5,
        grounded_count=4,
        requested_count=5,
    )
    assert result.publish_status == "draft_only_not_publish_ready"
    assert any("strict recommendations" in reason for reason in result.failure_reasons)


def test_editorial_invalid_or_compound_recommendation_hard_fails():
    result = _final(
        contract=_contract("7 best perfumes for summer", 7),
        article_count=7,
        grounded_count=4,
        requested_count=7,
        recommendation_audit={
            "invalid_recommendations": [
                "Dolce & Gabbana Light Blue or Gucci Flora"
            ]
        },
    )
    assert result.publish_status == "draft_only_not_publish_ready"


def test_editorial_title_count_mismatch_hard_fails():
    result = _final(
        contract=_contract("7 best perfumes for summer", 7),
        article_count=7,
        grounded_count=7,
        requested_count=7,
        title_count=5,
    )
    assert result.publish_status == "draft_only_not_publish_ready"


def test_candidate_pack_splits_or_compound():
    contract = _contract("2 best perfumes for summer", 2).model_copy(
        update={"minimum_publishable_items": 2}
    )
    compound = _candidate(
        "Dolce & Gabbana Light Blue or Gucci Flora",
        1,
    )
    pack = build_candidate_pack(contract, _ledger([compound], 2))
    assert pack.mode == "editorial_shortlist"
    assert pack.status == "exact"
    assert len(pack.items) == 2
    names = {item.display_name.lower() for item in pack.items}
    assert any("light blue" in name for name in names)
    assert any("gucci flora" in name for name in names)


def test_candidate_pack_splits_and_compound_when_both_products_are_valid():
    contract = _contract("2 best perfumes for summer", 2).model_copy(
        update={"minimum_publishable_items": 2}
    )
    compound = _candidate("Paris-Biarritz and Paris-Riviera", 1)
    pack = build_candidate_pack(contract, _ledger([compound], 2))
    assert len(pack.items) == 2
    assert {item.display_name.lower() for item in pack.items} == {
        "paris-biarritz",
        "paris-riviera",
    }


def test_candidate_pack_rejects_brand_cluster():
    contract = _contract("7 best perfumes for summer", 7)
    cluster = _candidate("ARMANI PRADA Paco Rabanne CREED CALVIN", 1)
    pack = build_candidate_pack(contract, _ledger([cluster], 7))
    assert pack.items == []
    assert pack.status == "below_minimum"


def test_editorial_skeleton_avoids_compliance_memo_language():
    contract = _contract("3 best perfumes for summer", 3)
    candidates = [_candidate(f"Perfume {index}", index) for index in range(1, 4)]
    pack = build_candidate_pack(contract, _ledger(candidates, 3))
    article = build_candidate_locked_recommendation_skeleton(
        contract, pack, "perfumes for summer"
    ).lower()
    forbidden = (
        "source-backed recommendations",
        "evidence-limited",
        "validated candidates",
        "available evidence supported",
        "rigorous evidence",
    )
    assert all(phrase not in article for phrase in forbidden)
    assert "our picks" in article


def test_ui_contains_editorial_review_status_and_badges():
    html = _build_app_html()
    assert "publish_ready_with_editorial_review" in html
    assert "Copy-ready after light review" in html
    assert "content-first" in html
    assert "editorial picks" in html
    assert "source-aware" in html
    assert "review recommended" in html
