"""Tests for CandidatePackQualityReport — the pre-draft candidate integrity gate.

This gate runs on the locked CandidatePack before the writer drafts the article.
It must catch dirty display names, invalid entities (people/authors/dates/etc via
the domain adapter), light-coverage candidates, and missing evidence — and assign
a publish_ceiling and repair_action accordingly.
"""

from __future__ import annotations

from blogagent.tools.candidate_pack import (
    CandidatePack,
    CandidatePackItem,
    CandidatePackQualityReport,
    build_candidate_pack_quality_report,
)
from blogagent.workflow.query_contract import build_query_contract


def _contract(requested: int | None = 5, strictness: str | None = None):
    contract = build_query_contract(
        "best automatic watches under $2000",
        is_recommendation=True,
        is_financial=False,
        requested_count=requested,
    )
    if strictness is not None:
        contract = contract.model_copy(update={"recommendation_strictness": strictness})
    return contract


def _item(
    name: str,
    index: int,
    *,
    evidence_spans: list[str] | None = None,
    candidate_basis: str = "source_exact",
    entity_type: str = "specific_product",
) -> CandidatePackItem:
    return CandidatePackItem(
        candidate_id=f"cand-{index}",
        canonical_name=name,
        display_name=name,
        section_heading=name,
        source_url=f"https://example.com/{index}",
        source_title=f"Source {index}",
        source_quality="high",
        source_type="editorial",
        evidence_spans=evidence_spans if evidence_spans is not None else [f"{name} review notes."],
        evidence_terms=["daily wear"],
        supported_context=["everyday wear"],
        entity_type=entity_type,
        entity_subtype="watch_product",
        candidate_confidence="high",
        candidate_basis=candidate_basis,
        needs_review=False,
    )


def _pack(items: list[CandidatePackItem], requested: int | None = 5, status: str = "exact"):
    return CandidatePack(
        requested_count=requested,
        allowed_count=len(items),
        final_target_count=len(items),
        mode="exact",
        status=status,
        recommendation_strictness="standard",
        evidence_mode="source_aware",
        minimum_publishable_items=3,
        evidence_limited=False,
        items=items,
        count_policy="exact",
        locked_candidate_ids=[i.candidate_id for i in items],
        locked_display_names=[i.display_name for i in items],
    )


# ---------------------------------------------------------------------------
# Clean pack passes
# ---------------------------------------------------------------------------


def test_clean_exact_pack_passes_with_publish_ready_ceiling():
    items = [_item(f"Watch Brand {i}", i) for i in range(5)]
    pack = _pack(items, requested=5, status="exact")
    # Force "standard" strictness so the report exercises the "exact" branch —
    # this topic defaults to "editorial" strictness, which routes through the
    # editorial_shortlist branch instead.
    report = build_candidate_pack_quality_report(pack, _contract(5, strictness="standard"))

    assert isinstance(report, CandidatePackQualityReport)
    assert report.passes is True
    assert report.locked_count == 5
    assert report.requested_count == 5
    assert not report.invalid_items
    assert not report.dirty_name_items
    assert report.mode == "exact"
    assert report.publish_ceiling == "publish_ready"
    assert report.repair_action == "proceed"


# ---------------------------------------------------------------------------
# Dirty display names block exact mode
# ---------------------------------------------------------------------------


def test_dirty_display_names_are_caught_and_block_exact_mode():
    # These names look like plausible Brand+Model products (so they pass the
    # domain adapter's is_valid_entity string-pattern check) but carry nav/debris
    # fragments that _is_dirty_display_name must catch before they reach an article.
    items = [
        _item("Watch Brand 0", 0),
        _item("Tissot PRX Watch Photos", 1),  # nav fragment: "photos"
        _item("Hamilton Khaki Field Review", 2),  # nav fragment: "review"
    ]
    pack = _pack(items, requested=3, status="exact")
    report = build_candidate_pack_quality_report(pack, _contract(3, strictness="standard"))

    assert report.passes is False
    assert report.dirty_name_items
    assert "Tissot PRX Watch Photos" in report.dirty_name_items
    assert "Hamilton Khaki Field Review" in report.dirty_name_items
    assert report.mode == "failed"
    assert report.publish_ceiling == "draft_only_not_publish_ready"
    assert report.repair_action == "repair_candidates"


# ---------------------------------------------------------------------------
# Invalid entity names (per domain adapter string-pattern checks) block exact mode
# ---------------------------------------------------------------------------


def test_invalid_entity_names_are_caught_via_domain_adapter():
    # The domain adapter validates the NAME STRING shape (brand+model patterns),
    # not the `entity_type` field. A bare brand name with no model ("Seiko") is
    # rejected by the adapter's brand-only heuristic and must land in invalid_items.
    items = [
        _item("Watch Brand 0", 0),
        _item("Seiko", 1),
    ]
    pack = _pack(items, requested=2, status="exact")
    report = build_candidate_pack_quality_report(pack, _contract(2, strictness="standard"))

    assert report.passes is False
    assert report.invalid_items
    assert "Seiko" in report.invalid_items
    assert report.mode == "failed"
    assert report.publish_ceiling == "draft_only_not_publish_ready"


# ---------------------------------------------------------------------------
# Missing evidence / light coverage
# ---------------------------------------------------------------------------


def test_missing_evidence_items_are_tracked():
    items = [
        _item("Watch Brand 0", 0),
        _item("Watch Brand 1", 1, evidence_spans=[]),
    ]
    pack = _pack(items, requested=2, status="exact")
    report = build_candidate_pack_quality_report(pack, _contract(2))

    assert "Watch Brand 1" in report.missing_evidence_items
    # Soft issues push the ceiling to editorial review, not a hard failure
    assert report.publish_ceiling == "publish_ready_with_editorial_review"
    assert report.passes is True


def test_light_coverage_items_from_editorial_discretion_basis_are_tracked():
    items = [
        _item("Watch Brand 0", 0),
        _item("Watch Brand 1", 1, candidate_basis="editorial_discretion"),
    ]
    pack = _pack(items, requested=2, status="exact")
    report = build_candidate_pack_quality_report(pack, _contract(2))

    assert "Watch Brand 1" in report.light_coverage_items
    assert report.publish_ceiling == "publish_ready_with_editorial_review"


# ---------------------------------------------------------------------------
# Editorial strictness allows light coverage without hard failure
# ---------------------------------------------------------------------------


def test_editorial_strictness_allows_light_coverage_as_editorial_shortlist():
    items = [
        _item("Watch Brand 0", 0, candidate_basis="editorial_discretion"),
        _item("Watch Brand 1", 1, candidate_basis="editorial_discretion"),
    ]
    pack = _pack(items, requested=2, status="exact")
    report = build_candidate_pack_quality_report(pack, _contract(2, strictness="editorial"))

    assert report.passes is True
    assert report.mode == "editorial_shortlist"
    assert report.publish_ceiling == "publish_ready_with_editorial_review"
    assert report.repair_action == "proceed"


# ---------------------------------------------------------------------------
# Below-minimum packs fail fast
# ---------------------------------------------------------------------------


def test_below_minimum_pack_fails_fast():
    items = [_item("Watch Brand 0", 0)]
    pack = _pack(items, requested=5, status="below_minimum")
    pack = pack.model_copy(update={"mode": "below_minimum"})
    report = build_candidate_pack_quality_report(pack, _contract(5))

    assert report.passes is False
    assert report.mode == "failed"
    assert report.publish_ceiling == "draft_only_not_publish_ready"
    assert report.repair_action == "fail_fast"


# ---------------------------------------------------------------------------
# Evidence-limited packs that meet the minimum proceed with editorial-review ceiling
# ---------------------------------------------------------------------------


def test_evidence_limited_pack_meeting_minimum_proceeds_with_review_ceiling():
    items = [_item(f"Watch Brand {i}", i) for i in range(4)]
    pack = _pack(items, requested=7, status="evidence_limited")
    report = build_candidate_pack_quality_report(pack, _contract(7))

    assert report.mode == "evidence_limited"
    assert report.passes is True
    assert report.publish_ceiling == "publish_ready_with_editorial_review"
    assert report.repair_action == "proceed"


def test_evidence_limited_pack_below_minimum_count_requires_enrichment():
    items = [_item("Watch Brand 0", 0), _item("Watch Brand 1", 1)]
    pack = _pack(items, requested=7, status="evidence_limited")
    report = build_candidate_pack_quality_report(pack, _contract(7))

    assert report.mode == "evidence_limited"
    assert report.passes is False
    assert report.repair_action == "enrich_search"


# ---------------------------------------------------------------------------
# Generic category/buying-guide phrases must never lock as specific products
# ---------------------------------------------------------------------------


def test_candidate_pack_never_locks_invalid_specific_products():
    """A generic phrase like "Best Luxury Watches" must be caught as invalid
    even though "Tissot PRX Quartz" and "Seiko 5 Sports" are valid named products."""
    items = [
        _item("Tissot PRX Quartz", 0),
        _item("Seiko 5 Sports", 1),
        _item("Best Luxury Watches", 2),
    ]
    pack = _pack(items, requested=3, status="exact")
    report = build_candidate_pack_quality_report(pack, _contract(3, strictness="standard"))

    assert report.passes is False
    assert "Best Luxury Watches" in report.invalid_items
    assert report.mode == "failed"
    assert report.publish_ceiling == "draft_only_not_publish_ready"
    assert report.repair_action == "repair_candidates"
