"""Deterministic contract audits for writer, revision, and polish handoffs."""

from __future__ import annotations

import re

from blogagent.tools.agent_handoffs import (
    PolishOutputAudit,
    ReviewDefect,
    ReviewPacket,
    RevisionOutputAudit,
    RevisionPlan,
    WriterOutputAudit,
)
from blogagent.tools.candidate_pack import CandidatePack
from blogagent.workflow.query_contract import QueryContract


def audit_writer_output(
    article_markdown: str,
    draft_output: object | None,
    candidate_pack: CandidatePack | dict,
    query_contract: QueryContract | dict,
) -> WriterOutputAudit:
    pack = _pack(candidate_pack)
    contract = _contract(query_contract)
    used_ids = _used_candidate_ids(article_markdown, draft_output, pack)
    missing = [cid for cid in pack.locked_candidate_ids if cid not in used_ids]
    unknown = _unknown_candidate_names(article_markdown, draft_output, pack)
    declared = _declared_count(article_markdown)
    quick_count = _quick_picks_count(article_markdown)
    detail_count = _detail_sections_count(article_markdown, pack)
    explanation = _has_evidence_limited_explanation(article_markdown)

    if pack.status == "below_minimum":
        passes = (
            "not publish-ready" in article_markdown.lower()
            or "not publish ready" in article_markdown.lower()
        )
    else:
        passes = (
            not missing
            and not unknown
            and quick_count == pack.final_target_count
            and detail_count == pack.final_target_count
            and (declared in (None, pack.final_target_count))
            and (
                pack.status != "evidence_limited"
                or contract.recommendation_strictness == "editorial"
                or explanation
            )
        )
    return WriterOutputAudit(
        used_candidate_ids=used_ids,
        missing_candidate_ids=missing,
        unknown_candidate_names=unknown,
        declared_count=declared,
        quick_picks_count=quick_count,
        detail_sections_count=detail_count,
        evidence_limited_explanation_present=explanation,
        passes_locked_structure=passes,
    )


def build_review_packet(
    article_markdown: str,
    writer_audit: WriterOutputAudit | dict,
    candidate_pack: CandidatePack | dict,
    query_contract: QueryContract | dict,
    entity_audit: object | None,
    answer_count_snapshot: object | None,
) -> ReviewPacket:
    audit = (
        writer_audit
        if isinstance(writer_audit, WriterOutputAudit)
        else WriterOutputAudit.model_validate(writer_audit)
    )
    pack = _pack(candidate_pack)
    contract = _contract(query_contract)
    defects: list[ReviewDefect] = []

    def add(
        defect_type: str,
        severity: str,
        expected,
        actual,
        required_fix: str,
        scope: str,
        candidate_id: str | None = None,
    ) -> None:
        defects.append(
            ReviewDefect(
                defect_id=f"review-{len(defects) + 1:02d}",
                type=defect_type,
                severity=severity,
                candidate_id=candidate_id,
                expected=expected,
                actual=actual,
                required_fix=required_fix,
                fix_scope=scope,
            )
        )

    for cid in audit.missing_candidate_ids:
        add(
            "missing_locked_candidate",
            "high",
            "present",
            "missing",
            "Restore the locked candidate in Quick Picks and its detail section.",
            "candidate",
            cid,
        )
    for name in audit.unknown_candidate_names:
        add(
            "unknown_recommendation",
            "high",
            "CandidatePack item",
            name,
            "Remove the unknown recommendation without removing locked candidates.",
            "candidate",
        )
    if pack.status != "below_minimum" and audit.quick_picks_count != pack.final_target_count:
        add(
            "quick_picks_count_mismatch",
            "high",
            pack.final_target_count,
            audit.quick_picks_count,
            "Rebuild Quick Picks from CandidatePack in locked order.",
            "structure",
        )
    if pack.status != "below_minimum" and audit.detail_sections_count != pack.final_target_count:
        add(
            "detail_sections_count_mismatch",
            "high",
            pack.final_target_count,
            audit.detail_sections_count,
            "Provide one distinct detail section for every locked candidate.",
            "structure",
        )
    if (
        pack.status != "below_minimum"
        and audit.declared_count is not None
        and audit.declared_count != pack.final_target_count
    ):
        add(
            "title_count_mismatch",
            "high",
            pack.final_target_count,
            audit.declared_count,
            "Rewrite the H1 to declare CandidatePack.final_target_count.",
            "metadata",
        )
    if (
        pack.status == "evidence_limited"
        and contract.recommendation_strictness != "editorial"
        and not audit.evidence_limited_explanation_present
    ):
        add(
            "missing_evidence_limited_explanation",
            "medium",
            "present",
            "missing",
            "Explain that source evidence supported fewer items than requested.",
            "evidence",
        )

    unsupported = _read_list(entity_audit, "unsupported_entities")
    for name in unsupported:
        add(
            "unsupported_entity",
            "medium" if contract.recommendation_strictness == "editorial" else "high",
            "source-grounded candidate",
            name,
            "Remove the unsupported entity and preserve the locked set.",
            "evidence",
        )
    snapshot_status = _read_value(answer_count_snapshot, "count_status")
    if snapshot_status == "failed" and not any(d.type.endswith("mismatch") for d in defects):
        failure_reason = str(_read_value(answer_count_snapshot, "failure_reason") or "")
        add(
            "answer_count_failed",
            (
                "medium"
                if contract.recommendation_strictness == "editorial"
                and "grounded count" in failure_reason.lower()
                else "high"
            ),
            pack.final_target_count,
            _read_value(answer_count_snapshot, "article_entities_count"),
            "Restore count coherence before editorial changes.",
            "structure",
        )

    contract_defects = [d for d in defects if d.fix_scope != "style"]
    contract_passes = not any(d.severity == "high" for d in contract_defects)
    editorial_passes = not any(d.fix_scope == "style" and d.severity == "high" for d in defects)
    if pack.status == "below_minimum":
        revision_mode = "draft_only"
    elif not defects:
        revision_mode = "none"
    elif len([d for d in defects if d.severity == "high"]) >= max(3, pack.final_target_count):
        revision_mode = "full_rewrite"
    else:
        revision_mode = "targeted_repair"
    passes = contract_passes and editorial_passes and revision_mode != "draft_only"
    return ReviewPacket(
        passes=passes,
        contract_passes=contract_passes,
        editorial_passes=editorial_passes,
        defects=defects,
        missing_candidate_ids=list(audit.missing_candidate_ids),
        unsupported_entities=unsupported + list(audit.unknown_candidate_names),
        required_revision_mode=revision_mode,
        reviewer_summary=(
            f"Contract {'passed' if contract_passes else 'failed'} with "
            f"{len([d for d in defects if d.severity == 'high'])} high-severity "
            f"defect(s) and {len(defects)} total defect(s)."
        ),
    )


def build_revision_plan(
    review_packet: ReviewPacket | dict,
    candidate_pack: CandidatePack | dict,
) -> RevisionPlan:
    review = (
        review_packet
        if isinstance(review_packet, ReviewPacket)
        else ReviewPacket.model_validate(review_packet)
    )
    pack = _pack(candidate_pack)
    strategy = (
        review.required_revision_mode
        if review.required_revision_mode != "none"
        else "targeted_repair"
    )
    sections_to_add: list[str] = []
    sections_to_rewrite: list[str] = []
    for defect in review.defects:
        if defect.type == "quick_picks_count_mismatch":
            sections_to_add.append("Quick Picks")
        elif defect.type in {"missing_locked_candidate", "detail_sections_count_mismatch"}:
            sections_to_add.append(defect.candidate_id or "locked candidate detail section")
        elif defect.type == "title_count_mismatch":
            sections_to_rewrite.append("H1")
        elif defect.type == "missing_evidence_limited_explanation":
            sections_to_rewrite.append("Intro")
    return RevisionPlan(
        revision_strategy=strategy,
        defects_to_fix=[d.defect_id for d in review.defects],
        locked_candidate_ids_to_preserve=list(pack.locked_candidate_ids),
        sections_to_add=list(dict.fromkeys(sections_to_add)),
        sections_to_rewrite=list(dict.fromkeys(sections_to_rewrite)),
        forbidden_changes=[
            "add, remove, merge, or rename locked candidates",
            "change CandidatePack mode or final_target_count",
            "invent evidence or remove source URLs",
            "silently delete an item whose evidence is incomplete",
        ],
    )


def audit_revision_output(
    revised_markdown: str,
    revision_output: object | None,
    revision_plan: RevisionPlan | dict,
    candidate_pack: CandidatePack | dict,
    query_contract: QueryContract | dict,
) -> RevisionOutputAudit:
    plan = (
        revision_plan
        if isinstance(revision_plan, RevisionPlan)
        else RevisionPlan.model_validate(revision_plan)
    )
    writer_audit = audit_writer_output(
        revised_markdown, revision_output, candidate_pack, query_contract
    )
    unresolved: list[str] = []
    for defect_id in plan.defects_to_fix:
        if not writer_audit.passes_locked_structure:
            unresolved.append(defect_id)
    resolved = [defect_id for defect_id in plan.defects_to_fix if defect_id not in unresolved]
    return RevisionOutputAudit(
        resolved_defect_ids=resolved,
        unresolved_defect_ids=unresolved,
        used_candidate_ids=writer_audit.used_candidate_ids,
        missing_candidate_ids=writer_audit.missing_candidate_ids,
        unknown_candidate_names=writer_audit.unknown_candidate_names,
        structure_preserved=writer_audit.passes_locked_structure,
        passes_locked_structure=writer_audit.passes_locked_structure and not unresolved,
    )


def audit_polish_output(
    polished_markdown: str,
    polish_output: object | None,
    candidate_pack: CandidatePack | dict,
    query_contract: QueryContract | dict,
) -> PolishOutputAudit:
    audit = audit_writer_output(
        polished_markdown, polish_output, candidate_pack, query_contract
    )
    pack = _pack(candidate_pack)
    count_changed = (
        pack.status != "below_minimum"
        and (
            audit.quick_picks_count != pack.final_target_count
            or audit.detail_sections_count != pack.final_target_count
            or audit.declared_count not in (None, pack.final_target_count)
        )
    )
    candidate_changed = bool(audit.missing_candidate_ids or audit.unknown_candidate_names)
    return PolishOutputAudit(
        structure_preserved=audit.passes_locked_structure,
        used_candidate_ids=audit.used_candidate_ids,
        missing_candidate_ids=audit.missing_candidate_ids,
        unknown_candidate_names=audit.unknown_candidate_names,
        count_changed=count_changed,
        candidate_list_changed=candidate_changed,
    )


def _pack(value: CandidatePack | dict) -> CandidatePack:
    return value if isinstance(value, CandidatePack) else CandidatePack.model_validate(value)


def _contract(value: QueryContract | dict) -> QueryContract:
    return value if isinstance(value, QueryContract) else QueryContract.model_validate(value)


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _used_candidate_ids(
    markdown: str, structured_output: object | None, pack: CandidatePack
) -> list[str]:
    ids: list[str] = []
    structured = _structured_entities(structured_output)
    structured_ids = {str(item.get("candidate_id", "")) for item in structured}
    structured_names = {_norm(str(item.get("name", ""))) for item in structured}
    article_norm = _norm(markdown)
    for item in pack.items:
        if (
            item.candidate_id in structured_ids
            or _norm(item.display_name) in structured_names
            or _norm(item.display_name) in article_norm
            or _norm(item.canonical_name) in article_norm
        ):
            ids.append(item.candidate_id)
    return ids


def _unknown_candidate_names(
    markdown: str, structured_output: object | None, pack: CandidatePack
) -> list[str]:
    if pack.status == "below_minimum":
        return []
    allowed_ids = set(pack.locked_candidate_ids)
    allowed_names = {_norm(item.display_name) for item in pack.items}
    unknown: list[str] = []
    for item in _structured_entities(structured_output):
        cid = str(item.get("candidate_id", ""))
        name = str(item.get("name", "")).strip()
        if cid and cid in allowed_ids:
            continue
        if name and any(_names_match(_norm(name), allowed) for allowed in allowed_names):
            continue
        if name:
            unknown.append(name)

    try:
        from blogagent.tools.recommendation_extractor import (  # noqa: PLC0415
            extract_recommendations_from_article,
        )

        for rec in extract_recommendations_from_article(markdown):
            rec_norm = _norm(rec.name)
            if not any(_names_match(rec_norm, allowed) for allowed in allowed_names):
                unknown.append(rec.name)
    except Exception:  # noqa: BLE001
        pass
    return list(dict.fromkeys(unknown))


def _structured_entities(output: object | None) -> list[dict]:
    if output is None:
        return []
    if isinstance(output, dict):
        raw = output.get("recommended_entities") or output.get("used_candidate_ids") or []
    else:
        raw = getattr(output, "recommended_entities", None) or []
    entities: list[dict] = []
    for item in raw:
        if isinstance(item, dict):
            entities.append(item)
        elif hasattr(item, "model_dump"):
            entities.append(item.model_dump())
        elif isinstance(item, str):
            entities.append({"candidate_id": item, "name": ""})
    return entities


def _names_match(left: str, right: str) -> bool:
    return left == right or (len(left) > 5 and left in right) or (len(right) > 5 and right in left)


def _quick_picks_count(markdown: str) -> int:
    match = re.search(
        r"^#{1,3}\s+Quick\s+Picks\s*$\n(.*?)(?=^#{1,3}\s+|\Z)",
        markdown,
        re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    if not match:
        return 0
    return len(
        re.findall(r"^\s*(?:[-*]|\d+[.)])\s+\S", match.group(1), re.MULTILINE)
    )


def _detail_sections_count(markdown: str, pack: CandidatePack) -> int:
    headings = [
        _norm(value)
        for value in re.findall(r"^#{2,3}\s+(.+?)\s*$", markdown, re.MULTILINE)
    ]
    count = 0
    for item in pack.items:
        name = _norm(item.display_name)
        if any(_names_match(name, re.sub(r"^\d+\s+", "", heading)) for heading in headings):
            count += 1
    return count


def _declared_count(markdown: str) -> int | None:
    match = re.search(r"^#\s+(.+)$", markdown, re.MULTILINE)
    if not match:
        return None
    number = re.search(r"\b(\d{1,3})\b", match.group(1))
    return int(number.group(1)) if number else None


def _has_evidence_limited_explanation(markdown: str) -> bool:
    lower = markdown.lower()
    phrases = (
        "evidence supported",
        "available evidence",
        "sources supported",
        "validated options",
        "rather than the",
        "fewer items",
        "evidence-limited",
    )
    return any(phrase in lower for phrase in phrases)


def _read_list(value: object | None, key: str) -> list[str]:
    raw = _read_value(value, key) or []
    return list(raw) if isinstance(raw, (list, tuple)) else []


def _read_value(value: object | None, key: str):
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)
