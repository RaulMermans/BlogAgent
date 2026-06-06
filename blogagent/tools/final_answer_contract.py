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

from blogagent.tools.recommendation_policy import (
    RecommendationStrictness,
    evidence_policy_for_domain,
)

FinalCountMode = Literal["exact", "evidence_limited", "failed", "not_applicable"]
PublishStatus = Literal[
    "publish_ready",
    "publish_ready_with_editorial_review",
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
    recommendation_strictness: RecommendationStrictness = "standard"
    evidence_mode: str = "source_aware"
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
    recommendation_audit: Optional[dict] = None,
) -> FinalAnswerContract:
    """Build the canonical risk-tiered post-polish publish contract."""
    contract_cfg = query_contract or {}
    task_type = contract_cfg.get("task_type", "unknown")
    answer_entity_type = contract_cfg.get("answer_entity_type", "general_answer")
    contract_requested_count = contract_cfg.get("requested_count")
    policy = evidence_policy_for_domain(contract_cfg.get("domain", "general"))
    strictness: RecommendationStrictness = contract_cfg.get(
        "recommendation_strictness", policy.strictness_level
    )
    evidence_mode = contract_cfg.get("evidence_mode", policy.evidence_mode)
    requires_count_checking = (
        is_recommendation
        and task_type == "recommendation"
        and (
            answer_entity_type not in ("general_answer", "concept", "unknown")
            or contract_requested_count is not None
        )
    )

    snap = answer_count_snapshot or {}
    requested_count: Optional[int] = snap.get("requested_count")
    count_status = str(snap.get("count_status", ""))
    draft_recommended_count = int(snap.get("recommended_entities_count") or 0)
    final_article_count = int(snap.get("article_entities_count") or 0)
    grounded_count = int(snap.get("grounded_entities_count") or 0)
    allowed_count = int((candidate_ledger_summary or {}).get("usable_count") or 0)
    if allowed_count == 0:
        allowed_count = int(snap.get("allowed_candidates_count") or 0)

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

    common = {
        "requested_count": requested_count,
        "allowed_count": allowed_count,
        "draft_recommended_count": draft_recommended_count,
        "final_article_count": final_article_count,
        "grounded_count": grounded_count,
        "quick_picks_count": quick_picks_count,
        "detail_sections_count": detail_sections_count,
        "title_declared_count": title_declared_count,
        "meta_declared_count": meta_declared_count,
        "recommendation_strictness": strictness,
        "evidence_mode": evidence_mode,
    }
    if not requires_count_checking:
        return FinalAnswerContract(
            **common,
            final_count_mode="not_applicable",
            publish_status=_sanitise_status(
                (publish_contract or {}).get("status", "publish_ready")
            ),
            failure_reasons=[],
            warning_reasons=[],
        )

    failure_reasons: list[str] = []
    warning_reasons: list[str] = []
    snap_reason = snap.get("failure_reason") or "answer_count_snapshot.count_status=failed"
    if count_status == "failed":
        grounding_only = "grounded count" in snap_reason.lower()
        if strictness == "editorial" and grounding_only:
            warning_reasons.append("Needs editorial review: light source coverage")
        elif (
            strictness == "standard"
            and grounding_only
            and grounded_count >= minimum_publishable_items
        ):
            warning_reasons.append("Some recommendations have light source coverage")
        else:
            failure_reasons.append(snap_reason)

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
    if allowed_count == 0 and final_article_count > 0:
        failure_reasons.append(
            f"allowed_count=0 but article has {final_article_count} recommendations"
        )

    if allowed_count > 0 and 0 < final_article_count < allowed_count:
        reason = f"Final article used {final_article_count} of {allowed_count} clean candidates"
        if strictness == "editorial":
            warning_reasons.append(reason)
        else:
            failure_reasons.append(reason)

    if final_article_count > 0 and grounded_count < final_article_count:
        if strictness == "strict":
            failure_reasons.append(
                f"grounded_count ({grounded_count}) < final_article_count "
                f"({final_article_count}): strict recommendations require direct grounding"
            )
        elif strictness == "standard" and grounded_count < minimum_publishable_items:
            failure_reasons.append(
                f"grounded_count ({grounded_count}) below minimum publishable "
                f"({minimum_publishable_items})"
            )
        else:
            warning_reasons.append(
                f"{final_article_count - grounded_count} recommendation(s) have "
                "light direct source coverage"
            )
    basis_counts = (candidate_ledger_summary or {}).get("candidate_basis_counts", {})
    review_candidate_count = int(
        (candidate_ledger_summary or {}).get("needs_review_count") or 0
    )
    review_candidate_count = max(
        review_candidate_count,
        int(basis_counts.get("known_entity") or 0)
        + int(basis_counts.get("editorial_discretion") or 0)
        + int(basis_counts.get("weak_signal") or 0),
    )
    if strictness == "editorial" and review_candidate_count > 0:
        warning_reasons.append(
            f"{review_candidate_count} editorial pick(s) should receive a final human review"
        )
    elif strictness == "standard" and int(basis_counts.get("known_entity") or 0) > 0:
        warning_reasons.append(
            f"{int(basis_counts.get('known_entity') or 0)} recommendation(s) use "
            "known-product validation"
        )

    if final_article_count > 0:
        if quick_picks_count == 0:
            failure_reasons.append("Quick Picks section missing from recommendation article")
        elif quick_picks_count != final_article_count:
            failure_reasons.append(
                f"Quick Picks has {quick_picks_count} items but article has "
                f"{final_article_count} recommendations"
            )
    if (
        quick_picks_count > 0
        and detail_sections_count > 0
        and quick_picks_count != detail_sections_count
    ):
        failure_reasons.append(
            f"Quick Picks has {quick_picks_count} items but {detail_sections_count} "
            "detail sections exist"
        )
    if (
        title_declared_count is not None
        and final_article_count > 0
        and title_declared_count != final_article_count
    ):
        failure_reasons.append(
            f"Title declares {title_declared_count} items but article has "
            f"{final_article_count} recommendations"
        )
    if final_article_count < minimum_publishable_items:
        failure_reasons.append(
            f"final_article_count ({final_article_count}) below minimum publishable "
            f"({minimum_publishable_items})"
        )
    if (
        requested_count is not None
        and final_article_count > 0
        and requested_count != final_article_count
    ):
        reason = f"Article delivers {final_article_count} of {requested_count} requested items"
        if strictness == "strict":
            failure_reasons.append(reason)
        elif title_declared_count in (None, final_article_count):
            warning_reasons.append(reason + "; the article was intentionally retitled")

    for defect in (publish_contract or {}).get("defects", []):
        if defect.get("severity") != "high":
            continue
        defect_type = defect.get("type", "")
        message = defect.get("message") or defect_type or "publish contract failed"
        if defect_type == "unsupported_recommendations" and strictness != "strict":
            warning_reasons.append(message)
        elif message not in failure_reasons:
            failure_reasons.append(message)
    invalid_recommendations = list(
        (recommendation_audit or {}).get("invalid_recommendations", [])
    )
    invalid_recommendations += (recommendation_audit or {}).get(
        "brand_only_recommendations", []
    )
    invalid_recommendations += (recommendation_audit or {}).get(
        "section_heading_false_positives", []
    )
    if invalid_recommendations:
        failure_reasons.append(
            "Invalid or malformed recommendations: "
            + ", ".join(dict.fromkeys(invalid_recommendations[:3]))
        )

    if failure_reasons:
        final_count_mode: FinalCountMode = "failed"
    elif count_status == "not_applicable":
        return FinalAnswerContract(
            **common,
            final_count_mode="not_applicable",
            publish_status=_sanitise_status(
                (publish_contract or {}).get("status", "publish_ready")
            ),
            failure_reasons=[],
            warning_reasons=warning_reasons,
        )
    elif count_status in {"satisfied", "evidence_limited"}:
        final_count_mode = (
            "evidence_limited"
            if count_status == "evidence_limited"
            or (
                requested_count is not None
                and requested_count != final_article_count
            )
            else "exact"
        )
        if count_status == "evidence_limited":
            warning_reasons.append(
                f"A tighter shortlist: {final_article_count} of "
                f"{requested_count if requested_count is not None else 'unspecified'} requested"
            )
    elif count_status == "":
        return FinalAnswerContract(
            **common,
            final_count_mode="not_applicable",
            publish_status=_sanitise_status(
                (publish_contract or {}).get("status", "draft_only_not_publish_ready")
            ),
            failure_reasons=[],
            warning_reasons=warning_reasons,
        )
    else:
        failure_reasons.append(f"count_status={count_status!r}: unresolvable publish status")
        final_count_mode = "failed"

    if final_count_mode == "exact" and not warning_reasons:
        publish_status: PublishStatus = "publish_ready"
    elif final_count_mode in {"exact", "evidence_limited"}:
        publish_status = "publish_ready_with_editorial_review"
    else:
        publish_status = "draft_only_not_publish_ready"
    return FinalAnswerContract(
        **common,
        final_count_mode=final_count_mode,
        publish_status=publish_status,
        failure_reasons=failure_reasons,
        warning_reasons=list(dict.fromkeys(warning_reasons)),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sanitise_status(status: str) -> PublishStatus:
    _VALID: set[str] = {
        "publish_ready",
        "publish_ready_with_editorial_review",
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
