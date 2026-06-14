from __future__ import annotations

from blogagent.tools.agent_handoffs import build_polish_handoff, build_writer_handoff
from blogagent.tools.candidate_pack import CandidatePack, CandidatePackItem
from blogagent.tools.handoff_auditor import (
    audit_polish_output,
    audit_revision_output,
    audit_writer_output,
    build_review_packet,
    build_revision_plan,
)
from blogagent.workflow.query_contract import build_query_contract


def _contract():
    return build_query_contract(
        "7 best parfums for summer",
        is_recommendation=True,
        is_financial=False,
        requested_count=7,
    )


def _pack(count: int = 3) -> CandidatePack:
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
            evidence_spans=[f"Perfume {i} is supported."],
            evidence_terms=["summer"],
            supported_context=["warm weather"],
            entity_type="specific_product",
            entity_subtype="fragrance_product",
        )
        for i in range(1, count + 1)
    ]
    return CandidatePack(
        requested_count=7,
        allowed_count=count,
        final_target_count=count,
        mode="evidence_limited",
        minimum_publishable_items=3,
        evidence_limited=True,
        items=items,
        rejected_items=[],
        count_policy="Use all candidates.",
        locked_candidate_ids=[item.candidate_id for item in items],
        locked_display_names=[item.display_name for item in items],
    )


def _article(pack: CandidatePack, *, omit_last: bool = False) -> str:
    items = pack.items[:-1] if omit_last else pack.items
    quick = "\n".join(f"- {item.display_name}" for item in items)
    details = "\n\n".join(
        f"## {index}. {item.display_name}\n\nSupported detail."
        for index, item in enumerate(items, start=1)
    )
    return (
        f"# {len(items)} Source-Backed Picks\n\n"
        f"The available evidence supported {len(items)} validated options rather than 7.\n\n"
        f"## Quick Picks\n\n{quick}\n\n## How We Chose\n\nEvidence.\n\n"
        f"{details}\n\n## Buying or Choosing Tips\n\nTips.\n\n"
        "## Final Takeaway\n\nTakeaway."
    )


def test_writer_handoff_locks_ids_structure_and_forbidden_actions():
    pack = _pack()
    handoff = build_writer_handoff(_contract().model_dump(), pack)
    assert handoff.output_contract["required_candidate_ids"] == pack.locked_candidate_ids
    assert any("Quick Picks" in item for item in handoff.required_structure)
    assert any("remove locked" in item for item in handoff.forbidden_actions)
    assert "evidence" in handoff.evidence_policy.lower()


def test_missing_locked_candidate_creates_high_review_defect():
    pack = _pack()
    article = _article(pack, omit_last=True)
    writer = audit_writer_output(article, None, pack, _contract())
    review = build_review_packet(article, writer, pack, _contract(), None, None)
    assert review.contract_passes is False
    assert any(
        defect.type == "missing_locked_candidate" and defect.severity == "high"
        for defect in review.defects
    )


def test_quick_picks_mismatch_creates_high_defect():
    pack = _pack()
    article = _article(pack).replace("- Perfume 3\n", "")
    writer = audit_writer_output(article, None, pack, _contract())
    review = build_review_packet(article, writer, pack, _contract(), None, None)
    assert any(defect.type == "quick_picks_count_mismatch" for defect in review.defects)


def test_unknown_structured_entity_creates_high_defect():
    pack = _pack()
    article = _article(pack)
    output = {"recommended_entities": [{"candidate_id": "x", "name": "Unknown Perfume"}]}
    writer = audit_writer_output(article, output, pack, _contract())
    review = build_review_packet(article, writer, pack, _contract(), None, None)
    assert "Unknown Perfume" in review.unsupported_entities
    assert any(defect.type == "unknown_recommendation" for defect in review.defects)


def test_reviewer_vetoes_invalid_candidate_pack():
    """An article that drops a locked candidate and substitutes an unknown
    recommendation must be vetoed by the reviewer with a non-passing revision mode."""
    pack = _pack(3)
    article = _article(pack, omit_last=True).replace(
        "## Buying or Choosing Tips",
        "## 3. Mystery Watch X\n\n"
        "This recommendation was never in the locked candidate table.\n\n"
        "## Buying or Choosing Tips",
    )
    writer = audit_writer_output(article, None, pack, _contract())
    review = build_review_packet(article, writer, pack, _contract(), None, None)
    assert review.passes is False
    assert any(defect.type == "missing_locked_candidate" for defect in review.defects)
    assert "c3" in review.missing_candidate_ids
    assert review.required_revision_mode in {"targeted_repair", "full_rewrite"}


def test_revision_does_not_polish_invalid_candidate_pack():
    """If the locked CandidatePack itself contains an invalid entity (e.g. a
    reviewer/dealer name like "Paul Altieri" mistaken for a product), the
    Reviewer must flag candidate_pack_valid=False and the revision plan must
    require a CandidatePack rebuild, not prose-only polish."""
    contract = build_query_contract(
        "best automatic watches under $2000",
        is_recommendation=True,
        is_financial=False,
        requested_count=4,
    )
    names = ["Tissot PRX Quartz", "Seiko 5 Sports", "Hamilton Khaki Field", "Paul Altieri"]
    items = [
        CandidatePackItem(
            candidate_id=f"cand-{i}",
            canonical_name=name,
            display_name=name,
            section_heading=name,
            source_url=f"https://example.com/{i}",
            source_title=f"Source {i}",
            source_quality="high",
            source_type="editorial",
            evidence_spans=[f"{name} review notes."],
            evidence_terms=["daily wear"],
            supported_context=["everyday wear"],
            entity_type="specific_product",
            entity_subtype="watch_product",
            candidate_confidence="high",
            candidate_basis="source_exact",
            needs_review=False,
        )
        for i, name in enumerate(names)
    ]
    pack = CandidatePack(
        requested_count=4,
        allowed_count=len(items),
        final_target_count=len(items),
        mode="exact",
        status="exact",
        recommendation_strictness="standard",
        evidence_mode="source_aware",
        minimum_publishable_items=3,
        evidence_limited=False,
        items=items,
        count_policy="exact",
        locked_candidate_ids=[item.candidate_id for item in items],
        locked_display_names=[item.display_name for item in items],
    )
    quick = "\n".join(f"- {item.display_name}" for item in items)
    details = "\n\n".join(
        f"## {index}. {item.display_name}\n\nSupported detail."
        for index, item in enumerate(items, start=1)
    )
    article = (
        f"# {len(items)} Best Automatic Watches Under $2000\n\n"
        f"## Quick Picks\n\n{quick}\n\n## How We Chose\n\nEvidence.\n\n"
        f"{details}\n\n## Buying or Choosing Tips\n\nTips.\n\n"
        "## Final Takeaway\n\nTakeaway."
    )
    writer = audit_writer_output(article, None, pack, contract)
    review = build_review_packet(article, writer, pack, contract, None, None)

    assert review.candidate_pack_valid is False
    assert "Paul Altieri" in review.invalid_locked_candidates
    assert review.revision_mode == "candidate_pack_rebuild"

    plan = build_revision_plan(review, pack)
    assert plan.revision_strategy == "full_rewrite"
    assert any("rebuild the candidatepack" in change.lower() for change in plan.forbidden_changes)


def test_revision_plan_targets_exact_defects_and_preserves_ids():
    pack = _pack()
    article = _article(pack, omit_last=True)
    writer = audit_writer_output(article, None, pack, _contract())
    review = build_review_packet(article, writer, pack, _contract(), None, None)
    plan = build_revision_plan(review, pack)
    assert set(plan.defects_to_fix) == {defect.defect_id for defect in review.defects}
    assert plan.locked_candidate_ids_to_preserve == pack.locked_candidate_ids


def test_revision_audit_fails_missing_candidates_and_passes_preserved_article():
    pack = _pack()
    bad = _article(pack, omit_last=True)
    writer = audit_writer_output(bad, None, pack, _contract())
    review = build_review_packet(bad, writer, pack, _contract(), None, None)
    plan = build_revision_plan(review, pack)
    bad_audit = audit_revision_output(bad, None, plan, pack, _contract())
    good_audit = audit_revision_output(_article(pack), None, plan, pack, _contract())
    assert bad_audit.passes_locked_structure is False
    assert bad_audit.unresolved_defect_ids
    assert good_audit.passes_locked_structure is True
    assert good_audit.unresolved_defect_ids == []


def test_polish_handoff_and_audit_forbid_candidate_drift():
    pack = _pack()
    handoff = build_polish_handoff(_article(pack), pack)
    assert handoff.locked_candidate_ids == pack.locked_candidate_ids
    assert any("remove" in item for item in handoff.forbidden_changes)
    preserved = audit_polish_output(_article(pack), None, pack, _contract())
    removed = audit_polish_output(_article(pack, omit_last=True), None, pack, _contract())
    assert preserved.structure_preserved is True
    assert removed.candidate_list_changed is True
    assert removed.count_changed is True
