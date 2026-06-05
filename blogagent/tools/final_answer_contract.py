"""Final Answer Contract — canonical post-polish publish status.

Builds a single deterministic object from the final article text, candidate
ledger, answer count snapshot, and publish contract.  This is the single
source of truth for publish_ready_status after all pipeline stages complete.

Key invariants:
- count_status=failed  → draft_only_not_publish_ready (always)
- allowed_count=0 with article>0 → draft_only_not_publish_ready
- final_article_count < allowed_count → draft_only_not_publish_ready
- quick_picks_count != final_article_count → draft_only_not_publish_ready
- title_declared_count != final_article_count → draft_only_not_publish_ready
- allowed_count is always sourced from candidate_ledger_summary, never from
  recommendation_candidates_summary (which over-counts via broad extraction)

Permission class: read_only
All operations are deterministic — no LLM calls.
"""

from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel

FinalCountMode = Literal["exact", "evidence_limited", "failed", "not_applicable"]
PublishStatus = Literal[
    "publish_ready",
    "publish_ready_with_warnings",
    "draft_only_not_publish_ready",
]


class FinalAnswerContract(BaseModel):
    """Canonical post-polish publish contract.

    Built after all pipeline stages complete (drafting, revision, polish,
    grounding, publish contract check).  Final authority for publish_ready_status
    and status badges shown in the UI.
    """

    requested_count: Optional[int]
    allowed_count: int
    draft_recommended_count: int
    final_article_count: int
    grounded_count: int
    quick_picks_count: int
    detail_sections_count: int
    title_declared_count: Optional[int]
    meta_declared_count: Optional[int]
    final_count_mode: FinalCountMode
    publish_status: PublishStatus
    failure_reasons: list[str]
    warning_reasons: list[str]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_final_answer_contract(
    article_markdown: str,
    title: str,
    meta_description: str,
    answer_count_snapshot: Optional[dict],
    candidate_ledger_summary: Optional[dict],
    query_contract: Optional[dict],
    publish_contract: Optional[dict],
    minimum_publishable_items: int = 3,
    is_recommendation: bool = False,
) -> FinalAnswerContract:
    """Build the canonical post-polish publish contract.

    Uses candidate_ledger_summary.usable_count as the authoritative source of
    allowed recommendations.  Never uses recommendation_candidates_summary
    (which can over-count via broad evidence extraction that pre-dates the
    Cleanliness Gate v2).
    """
    contract_cfg = query_contract or {}
    task_type = contract_cfg.get("task_type", "unknown")
    answer_entity_type = contract_cfg.get("answer_entity_type", "general_answer")
    contract_requested_count = contract_cfg.get("requested_count")

    requires_count_checking = (
        is_recommendation
        and task_type == "recommendation"
        and (
            answer_entity_type not in ("general_answer", "concept", "unknown")
            or contract_requested_count is not None
        )
    )

    # --- Extract counts from snapshot ---
    snap = answer_count_snapshot or {}
    requested_count: Optional[int] = snap.get("requested_count")
    count_status: str = snap.get("count_status", "")
    draft_recommended_count: int = int(snap.get("recommended_entities_count") or 0)
    final_article_count: int = int(snap.get("article_entities_count") or 0)
    grounded_count: int = int(snap.get("grounded_entities_count") or 0)

    # Allowed count: prefer candidate_ledger_summary (Cleanliness Gate v2).
    # Never use recommendation_candidates_summary.usable_count (broad extraction).
    allowed_count: int = 0
    if candidate_ledger_summary:
        allowed_count = int(candidate_ledger_summary.get("usable_count") or 0)
    if allowed_count == 0:
        # Fall back to snapshot (which is sourced from the ledger anyway)
        allowed_count = int(snap.get("allowed_candidates_count") or 0)

    # --- Extract article structure ---
    quick_picks_count = _count_quick_picks(article_markdown)
    detail_sections_count = _count_detail_sections(article_markdown)
    title_declared_count = (
        _extract_count_from_title(title)
        if title
        else _extract_count_from_markdown_title(article_markdown)
    )
    meta_declared_count = (
        _extract_count_from_text(meta_description) if meta_description else None
    )

    # --- not_applicable early return ---
    if not requires_count_checking:
        pc_status = _sanitise_status(
            (publish_contract or {}).get("status", "publish_ready")
        )
        return FinalAnswerContract(
            requested_count=requested_count,
            allowed_count=allowed_count,
            draft_recommended_count=draft_recommended_count,
            final_article_count=final_article_count,
            grounded_count=grounded_count,
            quick_picks_count=quick_picks_count,
            detail_sections_count=detail_sections_count,
            title_declared_count=title_declared_count,
            meta_declared_count=meta_declared_count,
            final_count_mode="not_applicable",
            publish_status=pc_status,
            failure_reasons=[],
            warning_reasons=[],
        )

    # --- Collect failure reasons ---
    failure_reasons: list[str] = []
    warning_reasons: list[str] = []

    # 1. Snapshot count_status=failed is always a failure.
    if count_status == "failed":
        snap_reason = snap.get("failure_reason") or "answer_count_snapshot.count_status=failed"
        failure_reasons.append(snap_reason)

    # 1b. Counted/concrete recommendation queries must have a candidate ledger.
    ledger_quality = (candidate_ledger_summary or {}).get("table_quality", "")
    if requested_count is not None and ledger_quality == "not_required":
        failure_reasons.append(
            "internal consistency failure: requested recommendation count exists but "
            "candidate ledger is not_required"
        )
    if count_status == "not_applicable" and requested_count is not None:
        failure_reasons.append(
            "internal consistency failure: counted recommendation query produced "
            "answer_count_snapshot.count_status=not_applicable"
        )
    if ledger_quality == "failed":
        failure_reasons.append("candidate ledger failed")

    # 2. allowed=0 with article>0 is an impossible state.
    if allowed_count == 0 and final_article_count > 0:
        failure_reasons.append(
            f"allowed_count=0 but article has {final_article_count} recommendations — "
            "impossible state: no allowed candidates but article contains recommendations"
        )

    # 3. Article used fewer items than allowed (includes the regression case:
    #    requested=7, allowed=5, article=3 → final_article_count(3) < allowed_count(5)).
    if allowed_count > 0 and 0 < final_article_count < allowed_count:
        failure_reasons.append(
            f"Final article used {final_article_count} of {allowed_count} allowed candidates. "
            "Article must use all allowed candidates."
        )

    # 4. Not all article recommendations are grounded.
    if final_article_count > 0 and grounded_count < final_article_count:
        failure_reasons.append(
            f"grounded_count ({grounded_count}) < final_article_count ({final_article_count}): "
            "not all article recommendations are grounded in source evidence"
        )

    # 5. Quick Picks missing or mismatched with article count.
    if final_article_count > 0:
        if quick_picks_count == 0:
            failure_reasons.append(
                "Quick Picks section missing from recommendation article"
            )
        elif quick_picks_count != final_article_count:
            failure_reasons.append(
                f"Quick Picks has {quick_picks_count} items but article has "
                f"{final_article_count} recommendations"
            )

    # 5b. Detail sections mismatch with Quick Picks (structural incoherence).
    if (
        quick_picks_count > 0
        and detail_sections_count > 0
        and quick_picks_count != detail_sections_count
    ):
        failure_reasons.append(
            f"Quick Picks has {quick_picks_count} items but {detail_sections_count} "
            "detail sections exist — structural mismatch"
        )

    # 6. Title declares a count different from what the article delivers.
    if title_declared_count is not None and final_article_count > 0:
        if title_declared_count != final_article_count:
            failure_reasons.append(
                f"Title declares {title_declared_count} items but article has "
                f"{final_article_count} recommendations — title must match final count"
            )

    # 7. Below minimum publishable items.
    if final_article_count < minimum_publishable_items:
        failure_reasons.append(
            f"final_article_count ({final_article_count}) below minimum publishable "
            f"({minimum_publishable_items})"
        )

    # --- Determine mode ---
    final_count_mode: FinalCountMode

    if failure_reasons:
        final_count_mode = "failed"
    elif count_status == "not_applicable":
        # Pipeline said not applicable for this contract shape — defer to publish contract.
        pc_status = _sanitise_status(
            (publish_contract or {}).get("status", "publish_ready")
        )
        return FinalAnswerContract(
            requested_count=requested_count,
            allowed_count=allowed_count,
            draft_recommended_count=draft_recommended_count,
            final_article_count=final_article_count,
            grounded_count=grounded_count,
            quick_picks_count=quick_picks_count,
            detail_sections_count=detail_sections_count,
            title_declared_count=title_declared_count,
            meta_declared_count=meta_declared_count,
            final_count_mode="not_applicable",
            publish_status=pc_status,
            failure_reasons=[],
            warning_reasons=[],
        )
    elif count_status == "satisfied":
        final_count_mode = "exact"
    elif count_status == "evidence_limited":
        final_count_mode = "evidence_limited"
        warning_reasons.append(
            f"Evidence-limited: {final_article_count} of "
            f"{requested_count if requested_count is not None else 'unspecified'} requested "
            f"({allowed_count} allowed candidates found)"
        )
    elif count_status == "":
        # Snapshot not built (very early failure or non-recommendation edge case).
        pc_status = _sanitise_status(
            (publish_contract or {}).get("status", "draft_only_not_publish_ready")
        )
        return FinalAnswerContract(
            requested_count=requested_count,
            allowed_count=allowed_count,
            draft_recommended_count=draft_recommended_count,
            final_article_count=final_article_count,
            grounded_count=grounded_count,
            quick_picks_count=quick_picks_count,
            detail_sections_count=detail_sections_count,
            title_declared_count=title_declared_count,
            meta_declared_count=meta_declared_count,
            final_count_mode="not_applicable",
            publish_status=pc_status,
            failure_reasons=[],
            warning_reasons=[],
        )
    else:
        # Unknown count_status — flag as failure.
        failure_reasons.append(
            f"count_status={count_status!r}: unresolvable publish status "
            f"(article={final_article_count}, allowed={allowed_count}, "
            f"requested={requested_count})"
        )
        final_count_mode = "failed"

    # --- Determine publish_status ---
    publish_status: PublishStatus
    if final_count_mode == "exact":
        publish_status = "publish_ready"
    elif final_count_mode == "evidence_limited":
        publish_status = "publish_ready_with_warnings"
    else:
        publish_status = "draft_only_not_publish_ready"

    return FinalAnswerContract(
        requested_count=requested_count,
        allowed_count=allowed_count,
        draft_recommended_count=draft_recommended_count,
        final_article_count=final_article_count,
        grounded_count=grounded_count,
        quick_picks_count=quick_picks_count,
        detail_sections_count=detail_sections_count,
        title_declared_count=title_declared_count,
        meta_declared_count=meta_declared_count,
        final_count_mode=final_count_mode,
        publish_status=publish_status,
        failure_reasons=failure_reasons,
        warning_reasons=warning_reasons,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sanitise_status(status: str) -> PublishStatus:
    _VALID: set[str] = {
        "publish_ready",
        "publish_ready_with_warnings",
        "draft_only_not_publish_ready",
    }
    return status if status in _VALID else "publish_ready"  # type: ignore[return-value]


def _count_quick_picks(markdown: str) -> int:
    """Count items in the Quick Picks section."""
    no_sources = re.split(
        r"\n#{1,3}\s*(?:Sources?|References?|Citations?|Further Reading)\s*\n",
        markdown,
        flags=re.IGNORECASE,
    )[0]
    m = re.search(
        r"#{1,3}\s*Quick\s*Picks\s*\n(.*?)(?=\n#{1,3}|\Z)",
        no_sources,
        re.DOTALL | re.IGNORECASE,
    )
    if not m:
        return 0
    section = m.group(1)
    bullets = re.findall(r"^\s*[-*]\s+\S", section, re.MULTILINE)
    numbered = re.findall(r"^\s*\d+[.)]\s+\S", section, re.MULTILINE)
    return len(bullets) + len(numbered)


def _count_detail_sections(markdown: str) -> int:
    """Count numbered H2/H3 recommendation sections."""
    no_sources = re.split(
        r"\n#{1,3}\s*(?:Sources?|References?|Citations?|Further Reading)\s*\n",
        markdown,
        flags=re.IGNORECASE,
    )[0]
    numbered = re.findall(r"^#{2,3}\s+\d+[.)]\s+\S", no_sources, re.MULTILINE)
    return len(numbered)


def _extract_count_from_title(title: str) -> Optional[int]:
    """Extract explicit count from a title like '7 Best…' or 'Top 5…'."""
    if not title:
        return None
    patterns = [
        r"\b(\d{1,2})\s+(?:best|top|great|essential|must-have|key|recommended|must)\b",
        r"\btop\s+(\d{1,2})\b",
        r"\bbest\s+(\d{1,2})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            n = int(match.group(1))
            if 1 <= n <= 50:
                return n
    return None


def _extract_count_from_markdown_title(markdown: str) -> Optional[int]:
    """Extract explicit count from the H1 title in article markdown."""
    title_m = re.search(r"^#\s+(.+)", markdown, re.MULTILINE)
    if not title_m:
        return None
    return _extract_count_from_title(title_m.group(1))


def _extract_count_from_text(text: str) -> Optional[int]:
    """Extract an explicit count from a description or meta text."""
    if not text:
        return None
    m = re.search(
        r"\b(\d{1,2})\s+(?:best|top|great|essential|recommendations?)\b",
        text,
        re.IGNORECASE,
    )
    if m:
        n = int(m.group(1))
        if 1 <= n <= 50:
            return n
    return None
