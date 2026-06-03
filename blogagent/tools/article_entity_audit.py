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

    Built after post-draft audit. Used by publish contract, run trace, and API.
    """

    requested_count: Optional[int]
    allowed_candidates_count: int
    article_entities_count: int
    grounded_entities_count: int
    evidence_limited: bool
    count_status: CountStatus


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
) -> AnswerCountSnapshot:
    """Build a unified answer count snapshot from audit results.

    This is the canonical count used by the publish contract, trace, and UI.
    Eliminates the '0 vs 7' and '25 vs 3' contradictions.
    """
    if not requires_candidate_ledger(query_contract):
        return AnswerCountSnapshot(
            requested_count=requested_count,
            allowed_candidates_count=0,
            article_entities_count=0,
            grounded_entities_count=0,
            evidence_limited=False,
            count_status="not_applicable",
        )

    allowed_count = len([c for c in allowed_candidates if c.get("usable", True)])
    article_count = entity_audit.article_entities_count if entity_audit else 0
    grounded_count = entity_audit.grounded_entities_count if entity_audit else 0

    # Determine count status
    count_status: CountStatus

    if requested_count is None:
        # No specific count requested — satisfied if we have minimum items
        if article_count >= minimum_publishable_items:
            count_status = "satisfied"
            evidence_limited = False
        elif article_count >= 1:
            count_status = "evidence_limited"
            evidence_limited = True
        else:
            count_status = "failed"
            evidence_limited = True
    else:
        if article_count >= requested_count:
            count_status = "satisfied"
            evidence_limited = False
        elif article_count >= minimum_publishable_items:
            count_status = "evidence_limited"
            evidence_limited = True
        else:
            count_status = "failed"
            evidence_limited = True

    return AnswerCountSnapshot(
        requested_count=requested_count,
        allowed_candidates_count=allowed_count,
        article_entities_count=article_count,
        grounded_entities_count=grounded_count,
        evidence_limited=evidence_limited,
        count_status=count_status,
    )
