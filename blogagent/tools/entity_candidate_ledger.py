"""Entity Candidate Ledger — generic answer-unit validation.

Wraps the existing recommendation candidate extraction with:
- Domain adapter-driven classification
- Pollution detection
- Ledger quality gate

Permission class: read_only
All operations are deterministic — no LLM calls.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel

from blogagent.tools.domain_adapters import get_adapter
from blogagent.workflow.query_contract import QueryContract, requires_candidate_ledger
from blogagent.workflow.state import EvidenceItem

LedgerQuality = Literal["strong", "limited", "failed", "not_required"]


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------


class EntityCandidate(BaseModel):
    """A validated entity candidate from the candidate ledger.

    Maps to the existing RecommendationCandidate but with richer typing
    to support generic domains.
    """

    raw_mention: str
    canonical_name: str = ""
    entity_type: str = "unknown"
    domain: str = "general"
    entity_subtype: Optional[str] = None
    source_urls: list[str] = []
    source_titles: list[str] = []
    source_quality: Literal["high", "medium", "low"] = "medium"
    source_type: str = "unknown"
    evidence_spans: list[str] = []
    evidence_terms: list[str] = []
    supported_context: list[str] = []
    clean_name_score: float = 0.0
    evidence_score: float = 0.0
    usable: bool = False
    rejection_reason: Optional[str] = None


class CandidateLedger(BaseModel):
    """Full candidate ledger for a query contract."""

    requested_count: Optional[int]
    raw_mentions_count: int
    candidates: list[EntityCandidate]
    validated_candidates: list[EntityCandidate]
    allowed_candidates: list[EntityCandidate]
    rejected_candidates: list[EntityCandidate]
    usable_count: int
    usable_names: list[str]
    rejected_count: int
    rejected_examples: list[dict]
    table_quality: LedgerQuality
    quality_issues: list[str]

    def to_summary_dict(self) -> dict:
        """Compact summary safe for API responses."""
        return {
            "requested_count": self.requested_count,
            "usable_count": self.usable_count,
            "rejected_count": self.rejected_count,
            "table_quality": self.table_quality,
            "quality_issues": list(self.quality_issues),
            "usable_names": list(self.usable_names[:10]),
            "rejected_examples": list(self.rejected_examples[:5]),
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_candidate_ledger(
    sources: list,
    evidence_table: list[EvidenceItem],
    query_contract: QueryContract,
    source_quality_scores: list[dict],
) -> CandidateLedger:
    """Build a candidate ledger from sources and evidence for a query contract.

    Delegates extraction to the existing recommendation_extractor for fragrance/general,
    then wraps results in the EntityCandidate/CandidateLedger models with quality analysis.

    Returns a ledger with table_quality = "not_required" for non-recommendation topics.
    """
    if not requires_candidate_ledger(query_contract):
        return CandidateLedger(
            requested_count=query_contract.requested_count,
            raw_mentions_count=0,
            candidates=[],
            validated_candidates=[],
            allowed_candidates=[],
            rejected_candidates=[],
            usable_count=0,
            usable_names=[],
            rejected_count=0,
            rejected_examples=[],
            table_quality="not_required",
            quality_issues=[],
        )

    from blogagent.tools.recommendation_extractor import (  # noqa: PLC0415
        RecommendationCandidate,
        extract_candidates_from_sources,
    )

    raw_candidates: list[RecommendationCandidate] = extract_candidates_from_sources(
        sources=sources,
        evidence_table=evidence_table,
        query_contract=query_contract,
        source_quality_scores=source_quality_scores,
    )

    candidates = [_to_entity_candidate(c, query_contract) for c in raw_candidates]
    allowed = [c for c in candidates if c.usable]
    rejected = [c for c in candidates if not c.usable]

    ledger = CandidateLedger(
        requested_count=query_contract.requested_count,
        raw_mentions_count=len(candidates),
        candidates=candidates,
        validated_candidates=allowed,
        allowed_candidates=allowed,
        rejected_candidates=rejected,
        usable_count=len(allowed),
        usable_names=[c.canonical_name or c.raw_mention for c in allowed],
        rejected_count=len(rejected),
        rejected_examples=[
            {
                "name": c.raw_mention,
                "entity_type": c.entity_type,
                "rejection_reason": c.rejection_reason,
            }
            for c in rejected[:10]
        ],
        table_quality="not_required",  # will be updated
        quality_issues=[],
    )

    return evaluate_candidate_ledger_quality(ledger, query_contract)


def evaluate_candidate_ledger_quality(
    ledger: CandidateLedger,
    query_contract: QueryContract,
) -> CandidateLedger:
    """Evaluate and set table_quality on the ledger.

    Quality rules:
    - strong: usable_count >= requested_count (if set), low pollution
    - limited: usable_count >= minimum_publishable_items but < requested_count
    - failed: usable_count < minimum_publishable_items OR pollution detected
    - not_required: non-recommendation task type
    """
    if not requires_candidate_ledger(query_contract):
        return ledger

    quality_issues: list[str] = []
    min_items = query_contract.minimum_publishable_items
    requested = query_contract.requested_count

    # --- Pollution checks ---
    pollution_count = _count_polluted(ledger)
    if pollution_count > 0:
        quality_issues.append(
            f"{pollution_count} polluted candidate(s) incorrectly marked usable"
        )

    # Percentage of raw mentions that are entity clusters / source nav / source titles
    if ledger.raw_mentions_count > 0:
        rejected_pollution = sum(
            1
            for c in ledger.rejected_candidates
            if c.entity_type in ("brand_cluster", "source_title", "source_nav", "section_heading")
        )
        pollution_ratio = rejected_pollution / ledger.raw_mentions_count
        if pollution_ratio > 0.2:
            quality_issues.append(
                f"High pollution ratio: {rejected_pollution}/{ledger.raw_mentions_count} "
                "raw mentions are entity clusters, source nav, or source titles"
            )

    # Average name length check (suspiciously long names signal cluster pollution)
    if ledger.allowed_candidates:
        avg_len = sum(len(c.raw_mention) for c in ledger.allowed_candidates) / len(
            ledger.allowed_candidates
        )
        if avg_len > 60:
            quality_issues.append(
                f"Average allowed candidate name length is {avg_len:.0f} chars — "
                "may contain cluster pollution"
            )

    # --- Determine quality level ---
    actual_usable = ledger.usable_count - pollution_count

    if pollution_count > 0:
        table_quality: LedgerQuality = "failed"
    elif actual_usable < min_items:
        table_quality: LedgerQuality = "failed"
        quality_issues.append(
            f"Usable count ({actual_usable}) is below minimum publishable ({min_items})"
        )
    elif requested is not None and actual_usable < requested:
        table_quality = "limited"
        quality_issues.append(
            f"Usable count ({actual_usable}) is below requested ({requested})"
        )
    else:
        table_quality = "strong"

    return ledger.model_copy(
        update={
            "table_quality": table_quality,
            "quality_issues": quality_issues,
            "usable_count": actual_usable,
        }
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _to_entity_candidate(
    candidate,  # RecommendationCandidate
    query_contract: QueryContract,
) -> EntityCandidate:
    """Convert a RecommendationCandidate to an EntityCandidate."""
    adapter = get_adapter(query_contract.domain)
    entity_type = adapter.classify_entity_type(candidate.name, query_contract)
    rejection_reason = adapter.get_rejection_reason(candidate.name, query_contract)
    usable = candidate.usable and rejection_reason is None
    if not usable and rejection_reason is None:
        rejection_reason = candidate.rejection_reason or "does not satisfy query contract"

    return EntityCandidate(
        raw_mention=candidate.name,
        canonical_name=adapter.canonicalize(candidate.name),
        entity_type=entity_type if entity_type != "unknown" else candidate.entity_type,
        domain=query_contract.domain,
        entity_subtype=query_contract.entity_subtype,
        source_urls=list(candidate.source_urls),
        source_titles=list(candidate.source_titles),
        source_quality=candidate.source_quality,
        source_type="editorial" if candidate.source_quality == "high" else "unknown",
        evidence_spans=[],
        evidence_terms=list(candidate.evidence_terms),
        supported_context=list(candidate.supported_context),
        clean_name_score=_compute_clean_name_score(candidate.name),
        evidence_score=_compute_evidence_score(candidate),
        usable=usable,
        rejection_reason=rejection_reason,
    )


def _compute_clean_name_score(name: str) -> float:
    """Score how 'clean' a candidate name is (0–1).

    Clean names are specific, not too long, not all caps.
    """
    if not name:
        return 0.0
    score = 1.0
    words = name.split()

    # Penalize very long names (likely entity clusters)
    if len(name) > 60:
        score -= 0.5
    elif len(name) > 40:
        score -= 0.2

    # Penalize single-word names (likely brand-only)
    if len(words) == 1:
        score -= 0.2

    # Penalize all-caps clusters (e.g. "ARMANI PRADA CREED")
    caps_words = sum(1 for w in words if w.isupper() and len(w) > 2)
    if caps_words >= 2:
        score -= 0.4

    return max(0.0, min(1.0, score))


def _compute_evidence_score(candidate) -> float:
    """Score how well-evidenced a candidate is (0–1)."""
    score = 0.0
    if candidate.source_quality == "high":
        score += 0.5
    elif candidate.source_quality == "medium":
        score += 0.3
    else:
        score += 0.1

    source_count = len(candidate.source_urls)
    score += min(0.3, source_count * 0.1)

    context_count = len(candidate.supported_context) + len(candidate.evidence_terms)
    score += min(0.2, context_count * 0.05)

    return min(1.0, score)


def _count_polluted(ledger: CandidateLedger) -> int:
    """Count allowed candidates that are actually polluted (entity clusters, headings, etc.)."""
    polluted_types = {"brand_cluster", "section_heading", "source_title", "source_nav"}
    return sum(1 for c in ledger.allowed_candidates if c.entity_type in polluted_types)
