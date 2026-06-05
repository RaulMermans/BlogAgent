"""Evidence Sufficiency Evaluator — deterministic pre-draft gate.

Permission class: read_only

Evaluates whether the retrieved evidence is sufficient to draft a quality article
before the drafting stage begins. For recommendation topics, this checks whether
enough named items exist to support the requested count.

All checks are deterministic — no LLM calls.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel

from blogagent.workflow.state import EvidenceItem

RecommendedAction = Literal["proceed", "search_more", "evidence_limited"]


class EvidenceSufficiencyResult(BaseModel):
    sufficient: bool
    score: int  # 0-100
    supported_count: int
    requested_count: Optional[int]
    missing: list[str]
    recommended_action: RecommendedAction


def evaluate_evidence_sufficiency(
    topic: str,
    requested_count: Optional[int],
    is_recommendation: bool,
    is_financial: bool,
    source_quality_scores: list[dict],
    evidence_table: list[EvidenceItem],
    enrichment_already_ran: bool = False,
    recommendation_candidates: Optional[list[dict]] = None,
) -> EvidenceSufficiencyResult:
    """Evaluate whether evidence is sufficient before drafting.

    When recommendation_candidates is provided, supported_count reflects actual
    usable named candidates rather than a source-count proxy.
    """
    missing: list[str] = []
    score = 100
    supported_count = 0

    if not is_recommendation:
        # For non-recommendation topics: minimal check — need at least 1 non-mock source
        real_sources = [
            s for s in source_quality_scores if s.get("quality") != "low" or not _is_mock_source(s)
        ]
        if len(real_sources) < 1:
            score -= 30
            missing.append("No credible sources found")
        return EvidenceSufficiencyResult(
            sufficient=score >= 50,
            score=score,
            supported_count=len(real_sources),
            requested_count=None,
            missing=missing,
            recommended_action="proceed",
        )

    # --- Recommendation topic checks ---
    high_medium = [s for s in source_quality_scores if s.get("quality") in ("high", "medium")]
    low_only = len(source_quality_scores) > 0 and len(high_medium) == 0

    # Count real (non-placeholder) evidence items
    real_evidence = [
        e
        for e in evidence_table
        if not e.fact.startswith("Information about") and len(e.fact.strip()) > 30
    ]

    # Use actual usable candidate count when candidates have been extracted;
    # fall back to the heuristic proxy only when candidates were not provided.
    if recommendation_candidates is not None:
        usable_candidates = [c for c in recommendation_candidates if c.get("usable")]
        supported_count = len(usable_candidates)
        # Invariant: if the candidate ledger produced zero usable candidates,
        # evidence is not sufficient regardless of source quality scores.
        if supported_count == 0:
            score = min(score, 59)
            missing.append(
                "Candidate ledger failed — no usable named entities extracted from sources"
            )
    else:
        # Legacy proxy: each high/medium source assumed to cover ~2 picks
        high_med_count = len(high_medium)
        supported_count = min(high_med_count * 2, len(real_evidence) + high_med_count)

    if requested_count is not None:
        if supported_count < requested_count:
            gap = requested_count - supported_count
            missing.append(
                f"Evidence supports {supported_count} usable recommendations; "
                f"{gap} more needed for {requested_count} requested"
            )
            score -= min(40, gap * 4)

    # Penalise low-source dominance
    if low_only or (
        len(source_quality_scores) > 0 and len(high_medium) / len(source_quality_scores) < 0.3
    ):
        score -= 20
        missing.append("Most sources are low-quality — editorial authority is weak")

    # Penalise thin evidence table
    if len(real_evidence) < 3:
        score -= 15
        missing.append(f"Only {len(real_evidence)} real evidence items found")

    score = max(0, score)
    sufficient = score >= 60 and (requested_count is None or supported_count >= requested_count)

    if not sufficient and requested_count is not None:
        if enrichment_already_ran:
            action: RecommendedAction = "evidence_limited"
        else:
            action = "search_more"
    elif not sufficient:
        action = "evidence_limited"
    else:
        action = "proceed"

    return EvidenceSufficiencyResult(
        sufficient=sufficient,
        score=score,
        supported_count=supported_count,
        requested_count=requested_count,
        missing=missing,
        recommended_action=action,
    )


def _is_mock_source(source_quality: dict) -> bool:
    """Return True if this source quality entry is for a mock placeholder."""
    reason = source_quality.get("reason", "")
    return "Mock placeholder" in reason or "mock" in reason.lower()


def generate_enrichment_queries(
    topic: str, missing: list[str], requested_count: Optional[int]
) -> list[str]:
    """Generate targeted search queries to fill evidence gaps for recommendation topics."""
    import re  # noqa: PLC0415

    base = topic.lower().strip()

    # Strip count prefixes to get the core subject
    cleaned = re.sub(r"\btop\s+\d+\s+", "", base)
    cleaned = re.sub(r"\bbest\s+\d+\s+", "", cleaned)
    cleaned = re.sub(r"\b\d+\s+best\s+", "", cleaned)
    cleaned = re.sub(r"\b\d+\s+top\s+", "", cleaned)
    cleaned = re.sub(r"\btop\s+", "", cleaned)
    cleaned = re.sub(r"\bbest\s+", "", cleaned)
    cleaned = cleaned.strip()

    # Fragrance / perfume domain: inject sensory-depth queries
    _FRAGRANCE_TERMS = ("perfume", "parfum", "fragrance", "cologne", "scent", "eau de")
    if any(t in base for t in _FRAGRANCE_TERMS):
        context = ""
        for ctx in ("summer", "date night", "winter", "spring", "evening", "office"):
            if ctx in base:
                context = ctx
                break
        if context:
            return [
                f"best {context} perfumes editor picks scent notes tested",
                f"top {context} fragrances reviewed notes longevity projection",
                f"{context} perfume recommendations scent family floral citrus fresh",
            ]
        return [
            f"best {cleaned} editor picks scent notes tested reviewed",
            f"top {cleaned} fragrances reviewed longevity projection",
            f"{cleaned} recommendations scent family notes occasion",
        ]

    # General recommendation queries
    queries = [
        f"best {cleaned} editor picks expert recommendations",
        f"top {cleaned} reviews tested",
        f"{cleaned} recommendations buying guide",
    ]
    return queries[:3]
