"""Publish Contract — final editorial truth layer.

Permission class: read_only
All checks are deterministic — no LLM calls.

This module applies hard-fail conditions AFTER the publishability evaluator
and editorial polish. It is the last gate before publish_ready_status is set.

Status levels:
  publish_ready                — score >= 85, no high defects, all hard checks pass
  publish_ready_with_warnings  — score >= 75, no high defects, evidence-limited
                                  framing accepted
  draft_only_not_publish_ready — score < 75 or any high defect remains
"""

from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------

ContractStatus = Literal[
    "publish_ready",
    "publish_ready_with_warnings",
    "draft_only_not_publish_ready",
]


class ContractDefect(BaseModel):
    type: str
    severity: Literal["low", "medium", "high"]
    message: str
    fixable: bool = False


class PublishContractResult(BaseModel):
    passes: bool
    status: ContractStatus
    score_cap: Optional[int]  # None = no cap; int = maximum allowed score
    defects: list[ContractDefect]
    summary: str


# ---------------------------------------------------------------------------
# Score caps per defect type
# ---------------------------------------------------------------------------

_SCORE_CAPS: dict[str, int] = {
    "unmet_requested_count": 59,  # requested count not met, no valid explanation
    "insufficient_recommendations": 65,  # fewer than 3 total recommendations
    "missing_quick_picks": 65,  # no Quick Picks section
    "unsupported_recommendations": 69,  # recommendations without source grounding
    "invalid_recommendations": 59,  # brand-only/headings/outside contract candidates
    "insufficient_validated_candidates": 65,
    "weak_source_dominance": 74,  # low-quality sources dominate core picks
    "weak_sensory_detail": 79,  # fragrance article with thin scent detail
    "generic_seo_voice": 79,  # generic intro / no editorial thesis
    "insufficient_recommendation_depth": 74,  # picks lack "best for" / why / context
    "thin_article": 65,  # article body is very short
}

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

_PUBLISH_READY_SCORE = 85
_PUBLISH_READY_WITH_WARNINGS_SCORE = 75


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_publish_contract(
    article_markdown: str,
    topic: str,
    publishability_score: int,
    publishability_defects: list[dict],
    is_recommendation: bool,
    requested_count: Optional[int],
    evidence_sufficiency: Optional[dict],
    source_quality_scores: list[dict],
    recommendation_grounding: Optional[dict] = None,
    query_contract: Optional[dict] = None,
    validated_candidates: Optional[list[dict]] = None,
    recommendation_audit: Optional[dict] = None,
    answer_count_snapshot: Optional[dict] = None,
) -> PublishContractResult:
    """Run hard-fail publish contract checks.

    Returns a PublishContractResult that is the final authority on publish status.

    recommendation_grounding (optional) is the output of post-article grounding:
    {
        "article_recommendations_count": int,
        "grounded_recommendations_count": int,
        "usable_count": int,
        "unmatched_names": list[str],
    }
    When provided, the contract uses article_recommendations_count as the primary count
    and grounded_recommendations_count to verify source backing.
    """
    defects: list[ContractDefect] = []
    score = publishability_score
    topic_lower = topic.lower()

    is_fragrance = any(
        kw in topic_lower for kw in ("perfume", "parfum", "fragrance", "cologne", "scent", "eau de")
    )

    # --- 1. Actual recommendation count ---
    # Prefer post-article grounding count; fall back to pattern count.
    grounding_article_count: Optional[int] = None
    grounding_grounded_count: Optional[int] = None
    grounding_unmatched: list[str] = []
    if recommendation_grounding:
        grounding_article_count = recommendation_grounding.get("article_recommendations_count")
        grounding_grounded_count = recommendation_grounding.get("grounded_recommendations_count")
        grounding_unmatched = recommendation_grounding.get("unmatched_names", [])
    contract = query_contract or {}
    min_publishable = int(contract.get("minimum_publishable_items") or 3)
    answer_entity_type = contract.get("answer_entity_type", "")
    entity_subtype = contract.get("entity_subtype", "")
    validated_candidates = validated_candidates or []
    usable_candidate_count = len([c for c in validated_candidates if c.get("usable", True)])

    # Use AnswerCountSnapshot when available — it's the canonical count
    snapshot_article_count: Optional[int] = None
    snapshot_count_status: str = ""
    snapshot_evidence_limited: bool = False
    if answer_count_snapshot:
        snapshot_article_count = answer_count_snapshot.get("article_entities_count")
        snapshot_count_status = answer_count_snapshot.get("count_status", "")
        snapshot_evidence_limited = bool(answer_count_snapshot.get("evidence_limited", False))
        grounding_article_count = snapshot_article_count or grounding_article_count
        # Sync grounding_grounded_count from snapshot
        snapshot_grounded = answer_count_snapshot.get("grounded_entities_count")
        if snapshot_grounded is not None:
            grounding_grounded_count = snapshot_grounded

    actual_count: Optional[int]
    if is_recommendation:
        if grounding_article_count is not None and grounding_article_count > 0:
            # Use grounding/snapshot count when available — derived from the final article
            actual_count = grounding_article_count
        else:
            actual_count = _count_recs(article_markdown)
    else:
        actual_count = None

    quick_picks_present = "Quick Picks" in article_markdown

    # --- 2. Missing Quick Picks section ---
    if is_recommendation and not quick_picks_present:
        defects.append(
            ContractDefect(
                type="missing_quick_picks",
                severity="high",
                message="Recommendation article has no Quick Picks section.",
                fixable=True,
            )
        )

    # --- 3. Fewer than 3 recommendations ---
    if is_recommendation and actual_count is not None and actual_count < min_publishable:
        defects.append(
            ContractDefect(
                type="insufficient_recommendations",
                severity="high",
                message=(
                    f"Article has only {actual_count} recommendation(s). "
                    f"A minimum of {min_publishable} is required for a publishable "
                    "recommendation list."
                ),
                fixable=False,
            )
        )

    if (
        is_recommendation
        and validated_candidates is not None
        and query_contract
        and usable_candidate_count < min_publishable
    ):
        defects.append(
            ContractDefect(
                type="insufficient_validated_candidates",
                severity="high",
                message=(
                    f"Only {usable_candidate_count} validated candidate(s) satisfy the query "
                    f"contract; minimum publishable count is {min_publishable}."
                ),
                fixable=False,
            )
        )

    # --- 4. Unmet requested count ---
    # Use snapshot count_status when available for coherent reporting
    evidence_limited_accepted = False
    if is_recommendation and requested_count is not None and actual_count is not None:
        if actual_count < requested_count:
            # When snapshot says "evidence_limited", treat as acceptable framing
            if snapshot_count_status == "evidence_limited" or snapshot_evidence_limited:
                evidence_limited_accepted = True
                defects.append(
                    ContractDefect(
                        type="unmet_requested_count",
                        severity="medium",
                        message=(
                            f"Article has {actual_count} of {requested_count} requested items. "
                            "Evidence-limited framing accepted."
                        ),
                        fixable=False,
                    )
                )
            else:
                has_explanation = _has_evidence_limited_explanation(article_markdown)
                title_falsely_claims = _title_falsely_claims_count(
                    article_markdown, requested_count
                )
                if has_explanation and not title_falsely_claims and actual_count >= min_publishable:
                    # Evidence-limited framing is acceptable
                    evidence_limited_accepted = True
                    defects.append(
                        ContractDefect(
                            type="unmet_requested_count",
                            severity="medium",
                            message=(
                                f"Article has {actual_count} of {requested_count} requested items. "
                                "Evidence-limited framing accepted."
                            ),
                            fixable=False,
                        )
                    )
                else:
                    defects.append(
                        ContractDefect(
                            type="unmet_requested_count",
                            severity="high",
                            message=(
                                f"Article has {actual_count} of {requested_count} requested items "
                                "without a clear evidence-limited explanation."
                            ),
                            fixable=True,
                        )
                    )

    # --- 4b. Unsupported recommendations (grounding failed) ---
    if is_recommendation and recommendation_audit:
        invalid_names = recommendation_audit.get("invalid_recommendations", [])
        unsupported_names = recommendation_audit.get("unsupported_recommendations", [])
        brand_only_names = recommendation_audit.get("brand_only_recommendations", [])
        section_false = recommendation_audit.get("section_heading_false_positives", [])
        grounded_allowed = int(recommendation_audit.get("grounded_recommendations_count") or 0)

        is_fragrance_product = (
            entity_subtype == "fragrance_product"
            or answer_entity_type == "specific_fragrance_product"
        )
        if is_fragrance_product and brand_only_names:
            defects.append(
                ContractDefect(
                    type="invalid_recommendations",
                    severity="high",
                    message=(
                        "Article includes brand-only recommendations where specific fragrance "
                        f"products are required: {', '.join(brand_only_names[:3])}."
                    ),
                    fixable=True,
                )
            )
        if section_false:
            defects.append(
                ContractDefect(
                    type="invalid_recommendations",
                    severity="high",
                    message=(
                        "Article counted section/source/category text as recommendations: "
                        f"{', '.join(section_false[:3])}."
                    ),
                    fixable=True,
                )
            )
        if unsupported_names:
            defects.append(
                ContractDefect(
                    type="unsupported_recommendations",
                    severity="high" if grounded_allowed < min_publishable else "medium",
                    message=(
                        "Article includes recommendations outside the allowed candidate table: "
                        f"{', '.join(unsupported_names[:3])}."
                    ),
                    fixable=True,
                )
            )
        elif invalid_names and not (brand_only_names or section_false):
            defects.append(
                ContractDefect(
                    type="invalid_recommendations",
                    severity="high",
                    message=(
                        "Article includes recommendations that do not satisfy the query contract: "
                        f"{', '.join(invalid_names[:3])}."
                    ),
                    fixable=True,
                )
            )
        if grounded_allowed < min_publishable:
            defects.append(
                ContractDefect(
                    type="insufficient_recommendations",
                    severity="high",
                    message=(
                        f"Only {grounded_allowed} article recommendation(s) are grounded in the "
                        f"allowed candidate table; minimum is {min_publishable}."
                    ),
                    fixable=False,
                )
            )

    if (
        is_recommendation
        and grounding_grounded_count is not None
        and grounding_article_count is not None
        and grounding_article_count > 0
    ):
        unmatched_count = grounding_article_count - grounding_grounded_count
        if unmatched_count > 0 and grounding_grounded_count < min_publishable:
            # Too few grounded recommendations to be publishable
            names_str = ", ".join(grounding_unmatched[:3])
            defects.append(
                ContractDefect(
                    type="unsupported_recommendations",
                    severity="high",
                    message=(
                        f"{unmatched_count} recommendation(s) could not be matched to source "
                        f"evidence and fewer than 3 are grounded. "
                        + (f"Unsupported: {names_str}" if names_str else "")
                    ),
                    fixable=False,
                )
            )
        elif unmatched_count > 0:
            names_str = ", ".join(grounding_unmatched[:3])
            defects.append(
                ContractDefect(
                    type="unsupported_recommendations",
                    severity="medium",
                    message=(
                        f"{unmatched_count} recommendation(s) could not be fully matched to "
                        f"source evidence."
                        + (f" Names: {names_str}" if names_str else "")
                    ),
                    fixable=True,
                )
            )

    # --- 5. Weak source dominance ---
    if source_quality_scores:
        low = sum(1 for s in source_quality_scores if s.get("quality") == "low")
        total = len(source_quality_scores)
        if total > 0 and low / total > 0.6:
            defects.append(
                ContractDefect(
                    type="weak_source_dominance",
                    severity="medium",
                    message=(
                        f"{low}/{total} sources are low-quality. "
                        "Core recommendations should be backed by editorial sources."
                    ),
                    fixable=False,
                )
            )

    # --- 6. Fragrance sensory detail ---
    if is_fragrance:
        sensory_count = _count_sensory_terms(article_markdown)
        if sensory_count < 3:
            defects.append(
                ContractDefect(
                    type="weak_sensory_detail",
                    severity="high",
                    message=(
                        f"Fragrance article mentions only {sensory_count} sensory term(s). "
                        "Include scent families, notes, or mood descriptions where "
                        "evidence supports."
                    ),
                    fixable=True,
                )
            )
        elif sensory_count < 6:
            defects.append(
                ContractDefect(
                    type="weak_sensory_detail",
                    severity="medium",
                    message=(
                        f"Fragrance article mentions {sensory_count} sensory terms — "
                        "could include more occasion/note/scent-family context."
                    ),
                    fixable=True,
                )
            )

    # --- 7. Recommendation depth (each pick needs "best for" / "why" context) ---
    if is_recommendation and actual_count and actual_count >= 3:
        depth_ok = _check_recommendation_depth(article_markdown)
        if not depth_ok:
            defects.append(
                ContractDefect(
                    type="insufficient_recommendation_depth",
                    severity="medium",
                    message=(
                        "Recommendation items lack 'best for', 'why it works', or "
                        "use-case context. Each pick should explain who it is for and why."
                    ),
                    fixable=True,
                )
            )

    # --- 8. Generic intro / no editorial thesis ---
    if _has_generic_intro(article_markdown) and not _has_editorial_pov(article_markdown):
        defects.append(
            ContractDefect(
                type="generic_seo_voice",
                severity="medium",
                message=(
                    "Intro is generic and article lacks a clear editorial POV. "
                    "Open with a specific observation or thesis."
                ),
                fixable=True,
            )
        )

    # --- 9. Thin article ---
    word_count = len(article_markdown.split())
    if word_count < 200:
        defects.append(
            ContractDefect(
                type="thin_article",
                severity="high",
                message=f"Article is very short ({word_count} words). Minimum 200 words required.",
                fixable=False,
            )
        )

    # --- Compute capped score ---
    # Score caps only apply for their relevant severity levels.
    # The most restrictive caps (unmet_requested_count: 59, missing_quick_picks: 65)
    # apply only on HIGH severity. Medium defects may apply softer caps.
    score_cap: Optional[int] = None
    for defect in defects:
        if defect.severity == "high":
            # Apply the cap for this defect type (if any)
            cap = _SCORE_CAPS.get(defect.type)
        else:
            # Medium/low defects: only apply caps for domain-critical defect types
            _MEDIUM_CAP_TYPES = {
                "weak_sensory_detail",
                "weak_source_dominance",
                "generic_seo_voice",
                "insufficient_recommendation_depth",
            }
            cap = _SCORE_CAPS.get(defect.type) if defect.type in _MEDIUM_CAP_TYPES else None
        if cap is not None:
            # Apply the most restrictive cap (lowest)
            if score_cap is None or cap < score_cap:
                score_cap = cap

    effective_score = min(score, score_cap) if score_cap is not None else score

    # --- Determine status ---
    high_defects = [d for d in defects if d.severity == "high"]
    if high_defects or effective_score < _PUBLISH_READY_WITH_WARNINGS_SCORE:
        status: ContractStatus = "draft_only_not_publish_ready"
        passes = False
    elif effective_score < _PUBLISH_READY_SCORE or evidence_limited_accepted:
        status = "publish_ready_with_warnings"
        passes = True
    else:
        status = "publish_ready"
        passes = True

    # --- Build summary ---
    if not defects:
        summary = f"Contract passed. Score: {effective_score}/100."
    else:
        msgs = "; ".join(d.message[:80] for d in defects[:3])
        more = f" (+{len(defects) - 3} more)" if len(defects) > 3 else ""
        cap_note = f" (score capped at {score_cap})" if score_cap else ""
        summary = (
            f"{status.replace('_', ' ').title()}. Score: {effective_score}/100"
            f"{cap_note}. {len(defects)} issue(s): {msgs}{more}"
        )

    return PublishContractResult(
        passes=passes,
        status=status,
        score_cap=score_cap,
        defects=defects,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FRAGRANCE_SENSORY_TERMS = (
    "notes",
    "base note",
    "top note",
    "heart note",
    "sillage",
    "longevity",
    "projection",
    "dry down",
    "scent family",
    "floral",
    "woody",
    "oriental",
    "fresh",
    "citrus",
    "musk",
    "amber",
    "oud",
    "spicy",
    "sweet",
    "powdery",
    "aquatic",
    "green",
    "leather",
    "sandalwood",
    "vetiver",
)

_GENERIC_INTRO_PHRASES = (
    "in the world of",
    "in today's world",
    "are you looking for",
    "look no further",
    "this article will",
    "this guide will",
    "whether you're a",
    "have you ever wondered",
    "it's no secret",
    "without further ado",
    "when it comes to",
    "in recent years",
    "in an ever-changing",
    "in today's competitive",
)

_POV_SIGNALS = (
    "the best",
    "worth",
    "avoid",
    "prefer",
    "recommend",
    "stand out",
    "winner",
    "top pick",
    "our pick",
    "editor's pick",
    "we love",
    "the winner",
    "our favorite",
    "surprisingly",
    "underrated",
    "overrated",
    "you should",
    "the real",
    "skip",
)

_EVIDENCE_LIMITED_PHRASES = (
    "available evidence",
    "supported by evidence",
    "available sources did not",
    "evidence-backed",
    "evidence supported only",
    "only supported",
    "insufficient evidence",
    "evidence did not support",
    "sources supported only",
    "sources did not provide enough",
    "only found",
    "we could only verify",
    "could only confirm",
    "with confidence",
    "enough coverage",
)


def _count_recs(markdown: str) -> int:
    """Count recommendations in the article."""
    # Strip source section
    no_sources = re.split(
        r"\n#{1,3}\s*(?:Sources?|References?|Citations?|Further Reading)\s*\n",
        markdown,
        flags=re.IGNORECASE,
    )[0]

    # Quick Picks bullets
    m = re.search(
        r"#{1,3}\s*Quick\s*Picks\s*\n(.*?)(?=\n#{1,3}|\Z)",
        no_sources,
        re.DOTALL | re.IGNORECASE,
    )
    if m:
        section = m.group(1)
        bullets = re.findall(r"^\s*[-*]\s+\S", section, re.MULTILINE)
        numbered = re.findall(r"^\s*\d+[.)]\s+\S", section, re.MULTILINE)
        count = len(bullets) + len(numbered)
        if count > 0:
            return count

    # Numbered H2/H3 headings
    numbered_headings = re.findall(r"^#{2,3}\s+\d+[.)]\s+\S", no_sources, re.MULTILINE)
    if numbered_headings:
        return len(numbered_headings)

    return 0


def _count_sensory_terms(markdown: str) -> int:
    lower = markdown.lower()
    return sum(1 for t in _FRAGRANCE_SENSORY_TERMS if t in lower)


def _has_evidence_limited_explanation(markdown: str) -> bool:
    lower = markdown.lower()
    return any(p in lower for p in _EVIDENCE_LIMITED_PHRASES)


def _title_falsely_claims_count(markdown: str, requested_count: int) -> bool:
    title_m = re.search(r"^#\s+(.+)", markdown, re.MULTILINE)
    if not title_m:
        return False
    title = title_m.group(1).lower()
    return f"top {requested_count}" in title or f"best {requested_count}" in title


def _check_recommendation_depth(markdown: str) -> bool:
    """Return True if at least some picks have 'best for', 'why', or use-case detail."""
    depth_signals = re.findall(
        r"(?:\*\*Best for\*\*|\*\*Why|Best for:|Why it works:|Caveat:|best for |perfect for )",
        markdown,
        re.IGNORECASE,
    )
    return len(depth_signals) >= 2


def _has_generic_intro(markdown: str) -> bool:
    intro = _extract_intro(markdown)
    lower = intro.lower()
    return sum(1 for p in _GENERIC_INTRO_PHRASES if p in lower) >= 1


def _has_editorial_pov(markdown: str) -> bool:
    lower = markdown.lower()
    return sum(1 for s in _POV_SIGNALS if s in lower) >= 2


def _extract_intro(markdown: str) -> str:
    lines = markdown.split("\n")
    found_title = False
    intro_lines: list[str] = []
    for line in lines:
        if line.startswith("# "):
            found_title = True
            continue
        if found_title:
            if line.startswith("##"):
                break
            if line.strip():
                intro_lines.append(line)
                if sum(len(ln) for ln in intro_lines) > 300:
                    break
    return " ".join(intro_lines)
