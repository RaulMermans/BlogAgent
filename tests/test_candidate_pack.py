from __future__ import annotations

from blogagent.tools.candidate_pack import build_candidate_pack
from blogagent.tools.entity_candidate_ledger import CandidateLedger, EntityCandidate
from blogagent.workflow.query_contract import build_query_contract


def _contract(requested: int | None = 7):
    return build_query_contract(
        "best parfums for summer",
        is_recommendation=True,
        is_financial=False,
        requested_count=requested,
    )


def _candidate(name: str, index: int, span: str | None = None) -> EntityCandidate:
    return EntityCandidate(
        candidate_id=f"cand-{index}",
        raw_mention=name,
        canonical_name=name,
        name=name,
        entity_type="specific_product",
        entity_subtype="fragrance_product",
        domain="beauty_fragrance",
        source_urls=[f"https://example.com/{index}"],
        source_titles=[f"Source {index}"],
        source_quality="high",
        source_type="editorial",
        evidence_spans=[span or f"{name} is included in the summer fragrance guide."],
        evidence_terms=["summer"],
        supported_context=["warm weather"],
        clean_name_score=0.95,
        evidence_score=0.9,
        usable=True,
    )


def _ledger(candidates: list[EntityCandidate]) -> CandidateLedger:
    return CandidateLedger(
        requested_count=7,
        raw_mentions_count=len(candidates),
        candidates=candidates,
        validated_candidates=candidates,
        allowed_candidates=candidates,
        rejected_candidates=[],
        usable_count=len(candidates),
        usable_names=[c.canonical_name for c in candidates],
        rejected_count=0,
        rejected_examples=[],
        table_quality="strong",
        quality_issues=[],
    )


def test_requested_seven_allowed_six_is_evidence_limited():
    pack = build_candidate_pack(
        _contract(7), _ledger([_candidate(f"Perfume {i}", i) for i in range(6)])
    )
    assert pack.mode == "editorial_shortlist"
    assert pack.status == "evidence_limited"
    assert pack.final_target_count == 6
    assert len(pack.locked_candidate_ids) == 6


def test_requested_five_allowed_five_is_exact():
    candidates = [_candidate(f"Perfume {i}", i) for i in range(5)]
    pack = build_candidate_pack(_contract(5), _ledger(candidates))
    assert pack.mode == "editorial_shortlist"
    assert pack.status == "exact"
    assert pack.final_target_count == 5


def test_allowed_below_minimum_is_below_minimum():
    pack = build_candidate_pack(
        _contract(7), _ledger([_candidate("Perfume One", 1), _candidate("Perfume Two", 2)])
    )
    assert pack.mode == "editorial_shortlist"
    assert pack.status == "below_minimum"
    assert pack.final_target_count == 2


def test_aliases_are_deduplicated_before_target_count():
    candidates = [
        _candidate("Soleil Blanc", 1, "Tom Ford Eau de Soleil Blanc is a summer fragrance."),
        _candidate(
            "Tom Ford Eau de Soleil Blanc",
            2,
            "Tom Ford Eau de Soleil Blanc is a summer fragrance.",
        ),
        _candidate("Light Blue", 3),
        _candidate("Neroli Portofino", 4),
    ]
    pack = build_candidate_pack(_contract(7), _ledger(candidates))
    assert pack.allowed_count == 3
    assert len([name for name in pack.locked_display_names if "Soleil Blanc" in name]) == 1


def test_display_name_completion_uses_evidence_span():
    candidate = _candidate(
        "dolce & gabbana light blue eau",
        1,
        "Dolce & Gabbana Light Blue Eau de Toilette is suited to summer.",
    )
    pack = build_candidate_pack(_contract(1), _ledger([candidate]))
    assert pack.items[0].display_name == "Dolce & Gabbana Light Blue Eau de Toilette"


def test_non_recommendation_is_not_applicable():
    contract = build_query_contract(
        "why elephants are large",
        is_recommendation=False,
        is_financial=False,
        requested_count=None,
    )
    pack = build_candidate_pack(contract, _ledger([]))
    assert pack.mode == "not_applicable"
    assert pack.items == []


def test_watch_candidate_gate_normalizes_display_names():
    """A messy raw mention with price/descriptor debris must be normalized for
    the article heading, e.g. "Hamilton Khaki Field Field Watch ~$695" ->
    "Hamilton Khaki Field"."""
    contract = build_query_contract(
        "1 best affordable luxury watch",
        is_recommendation=True,
        is_financial=False,
        requested_count=1,
    )
    candidate = EntityCandidate(
        candidate_id="cand-1",
        raw_mention="Hamilton Khaki Field Field Watch ~$695",
        canonical_name="Hamilton Khaki Field",
        name="Hamilton Khaki Field",
        entity_type="specific_product",
        domain="consumer_products",
        source_urls=["https://example.com/1"],
        source_titles=["Source 1"],
        source_quality="high",
        source_type="editorial",
        evidence_spans=["Hamilton Khaki Field is a popular affordable field watch."],
        evidence_terms=["everyday wear"],
        supported_context=["everyday wear"],
        clean_name_score=0.95,
        evidence_score=0.9,
        candidate_basis="known_entity",
        usable=True,
    )
    pack = build_candidate_pack(contract, _ledger([candidate]))
    assert pack.items[0].display_name == "Hamilton Khaki Field"
