"""Article Entity Audit — generic post-draft answer-unit validation.

Audits the final article against the allowed candidate table and produces
an EntityAudit + AnswerCountSnapshot.

This is the canonical, coherent count layer that eliminates the '0 vs 7'
and '25 vs 3' contradictions seen in the regression.

Permission class: read_only
All operations are deterministic — no LLM calls.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel

from blogagent.workflow.query_contract import QueryContract, requires_candidate_ledger

CountStatus = Literal["satisfied", "evidence_limited", "failed", "not_applicable"]


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------


class EntityAudit(BaseModel):
    """Result of auditing article entities against the allowed candidate table."""

    article_entities_count: int
    grounded_entities_count: int
    allowed_entities_count: int
    invalid_entities: list[str] = []
    unsupported_entities: list[str] = []
    brand_only_entities: list[str] = []
    section_heading_false_positives: list[str] = []
    model_introduced_source_grounded: list[str] = []
    passes: bool


class AnswerCountSnapshot(BaseModel):
    """Unified count snapshot — single source of truth for all count checks.

    Built after post-draft audit and draft candidate compliance check.
    Used by publish contract, run trace, and API.

    count_status rules:
      satisfied        — allowed >= requested, recommended == requested, grounded == requested
      evidence_limited — allowed < requested, article == allowed, allowed >= min, framing valid
      failed           — draft compliance failure, missing Quick Picks, count mismatch,
                         or grounded below minimum
      not_applicable   — non-recommendation topic
    """

    requested_count: Optional[int]
    allowed_candidates_count: int
    recommended_entities_count: int = 0
    article_entities_count: int
    grounded_entities_count: int
    evidence_limited: bool
    draft_candidate_compliance_passes: bool = True
    count_status: CountStatus
    failure_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def audit_article_entities(
    article_markdown: str,
    allowed_candidates: list[dict],
    query_contract: QueryContract,
    evidence_table: list,
    source_quality_scores: list[dict],
    source_scores: list | None = None,
) -> EntityAudit:
    """Audit article entities against the allowed candidate table.

    Wraps the existing audit_article_recommendations for recommendation topics.
    For non-recommendation topics, returns a trivially-passing audit.
    """
    if not requires_candidate_ledger(query_contract):
        return EntityAudit(
            article_entities_count=0,
            grounded_entities_count=0,
            allowed_entities_count=len(allowed_candidates),
            passes=True,
        )

    from blogagent.tools.recommendation_extractor import (  # noqa: PLC0415
        audit_article_recommendations,
    )
    from blogagent.workflow.state import EvidenceItem  # noqa: PLC0415

    evidence = [
        item if isinstance(item, EvidenceItem) else EvidenceItem.model_validate(item)
        for item in (evidence_table or [])
    ]

    rec_audit = audit_article_recommendations(
        markdown=article_markdown,
        allowed_candidates=allowed_candidates,
        query_contract=query_contract,
        evidence_table=evidence,
        source_quality_scores=source_quality_scores,
        source_scores=source_scores,
    )

    return EntityAudit(
        article_entities_count=rec_audit.article_recommendations_count,
        grounded_entities_count=rec_audit.grounded_recommendations_count,
        allowed_entities_count=len([c for c in allowed_candidates if c.get("usable", True)]),
        invalid_entities=list(rec_audit.invalid_recommendations),
        unsupported_entities=list(rec_audit.unsupported_recommendations),
        brand_only_entities=list(rec_audit.brand_only_recommendations),
        section_heading_false_positives=list(rec_audit.section_heading_false_positives),
        model_introduced_source_grounded=list(rec_audit.model_introduced_source_grounded),
        passes=rec_audit.passes,
    )


def build_answer_count_snapshot(
    requested_count: Optional[int],
    allowed_candidates: list[dict],
    entity_audit: Optional[EntityAudit],
    query_contract: QueryContract,
    minimum_publishable_items: int = 3,
    draft_candidate_compliance: Optional[object] = None,
) -> AnswerCountSnapshot:
    """Build a unified answer count snapshot from audit results.

    This is the canonical count used by the publish contract, trace, and UI.

    Key invariant:
    - If allowed_count >= requested_count but article used fewer → count_status=failed
      with defect_type=draft_candidate_compliance_failed (NOT evidence_limited)
    - If allowed_count < requested_count → evidence_limited=True
    """
    if not requires_candidate_ledger(query_contract):
        return AnswerCountSnapshot(
            requested_count=requested_count,
            allowed_candidates_count=0,
            recommended_entities_count=0,
            article_entities_count=0,
            grounded_entities_count=0,
            evidence_limited=False,
            draft_candidate_compliance_passes=True,
            count_status="not_applicable",
        )

    allowed_count = len([c for c in allowed_candidates if c.get("usable", True)])
    article_count = entity_audit.article_entities_count if entity_audit else 0
    grounded_count = entity_audit.grounded_entities_count if entity_audit else 0

    # Hard invariant: if allowed=0 for recommendation topic, the count cannot be satisfied.
    # The candidate ledger failed — any article recommendations are unsupported.
    if allowed_count == 0:
        # Extract compliance passes/failure for reporting
        comp_passes = True
        comp_failure: Optional[str] = None
        comp_recommended = article_count
        if draft_candidate_compliance is not None:
            comp_passes = bool(getattr(draft_candidate_compliance, "passes", True))
            comp_failure = getattr(draft_candidate_compliance, "failure_reason", None)
            comp_recommended = int(
                getattr(draft_candidate_compliance, "recommended_count", article_count) or 0
            )
        return AnswerCountSnapshot(
            requested_count=requested_count,
            allowed_candidates_count=0,
            recommended_entities_count=comp_recommended,
            article_entities_count=article_count,
            grounded_entities_count=grounded_count,
            evidence_limited=True,
            draft_candidate_compliance_passes=comp_passes,
            count_status="failed",
            failure_reason=(
                comp_failure or "no allowed candidates — candidate ledger quality gate failed"
            ),
        )

    # Extract compliance info
    compliance_passes = True
    compliance_failure_reason: Optional[str] = None
    recommended_count = article_count
    if draft_candidate_compliance is not None:
        compliance_passes = bool(getattr(draft_candidate_compliance, "passes", True))
        recommended_count = int(
            getattr(draft_candidate_compliance, "recommended_count", article_count) or 0
        )
        if not compliance_passes:
            compliance_failure_reason = getattr(draft_candidate_compliance, "failure_reason", None)

    # Determine count status
    count_status: CountStatus
    evidence_limited = False
    failure_reason: Optional[str] = None

    if requested_count is None:
        # No specific count requested — satisfied if we have minimum items
        if article_count >= minimum_publishable_items:
            count_status = "satisfied"
        elif article_count >= 1:
            count_status = "evidence_limited"
            evidence_limited = True
        else:
            count_status = "failed"
            evidence_limited = True
            failure_reason = "no recommendations detected in article"
    else:
        if allowed_count >= requested_count:
            # Enough candidates exist — any shortfall is a DRAFT compliance failure
            if not compliance_passes:
                count_status = "failed"
                failure_reason = compliance_failure_reason or "draft_candidate_compliance_failed"
            elif recommended_count != requested_count:
                count_status = "failed"
                failure_reason = (
                    f"draft_candidate_compliance_failed: recommended_entities_count "
                    f"{recommended_count}/{requested_count}"
                )
            elif article_count != requested_count:
                count_status = "failed"
                failure_reason = (
                    f"article count mismatch: article has {article_count}/{requested_count}"
                )
            elif grounded_count != requested_count:
                count_status = "failed"
                failure_reason = (
                    f"grounded count mismatch: grounded {grounded_count}/{requested_count}"
                )
            else:
                count_status = "satisfied"
        else:
            # Fewer allowed candidates than requested → evidence-limited
            evidence_limited = True
            if allowed_count < minimum_publishable_items:
                count_status = "failed"
                failure_reason = (
                    f"allowed candidate count {allowed_count} is below minimum "
                    f"publishable {minimum_publishable_items}"
                )
            elif (
                recommended_count == allowed_count
                and article_count == allowed_count
                and grounded_count >= minimum_publishable_items
                and compliance_passes
            ):
                count_status = "evidence_limited"
            else:
                count_status = "failed"
                failure_reason = (
                    compliance_failure_reason
                    or f"evidence-limited count mismatch: recommended={recommended_count}, "
                    f"article={article_count}, grounded={grounded_count}, allowed={allowed_count}"
                )

    return AnswerCountSnapshot(
        requested_count=requested_count,
        allowed_candidates_count=allowed_count,
        recommended_entities_count=recommended_count,
        article_entities_count=article_count,
        grounded_entities_count=grounded_count,
        evidence_limited=evidence_limited,
        draft_candidate_compliance_passes=compliance_passes,
        count_status=count_status,
        failure_reason=failure_reason,
    )
