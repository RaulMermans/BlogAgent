"""Quality Evaluator — deterministic quality checks on a blog draft.

Permission class: read_only

All checks are deterministic code — no LLM. The evaluator inspects the draft,
topic, evidence table, warnings, intent flags, and source quality data to
produce a structured QualityEvaluationOutput.

A revision is required when any high-severity defect is present.
"""

from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel

from blogagent.workflow.state import (
    EvidenceItem,
    SourceScore,
)

# ---------------------------------------------------------------------------
# Output schemas
# ---------------------------------------------------------------------------


class QualityDefect(BaseModel):
    type: str
    severity: Literal["low", "medium", "high"]
    message: str
    fixable: bool = False


class QualityEvaluationOutput(BaseModel):
    passes: bool
    score: int  # 0–100
    revision_required: bool
    defects: list[QualityDefect]
    summary: str


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def evaluate_quality(
    topic: str,
    draft: str,
    evidence_table: list[EvidenceItem],
    source_scores: list[SourceScore],
    source_quality_scores: list[dict],
    warnings: list[str],
    is_recommendation: bool,
    is_financial: bool,
    requested_count: Optional[int],
    selected_skills: list[str],  # noqa: ARG001 — reserved for future skill-aware checks
    review_packet: Optional[dict] = None,
) -> QualityEvaluationOutput:
    """Run all deterministic quality checks and return a structured report."""
    defects: list[QualityDefect] = []
    score = 100

    # Contract-first structured review. These defects dominate style scoring.
    if review_packet:
        for defect in review_packet.get("defects", []):
            defects.append(
                QualityDefect(
                    type=defect.get("type", "handoff_contract"),
                    severity=defect.get("severity", "high"),
                    message=defect.get("required_fix", "Repair the structured handoff defect."),
                    fixable=defect.get("fix_scope") != "safety",
                )
            )
        if not review_packet.get("contract_passes", True):
            score = min(score, 59)

    # --- 1. Top-N count mismatch (recommendation only) ---
    # Use the rich extractor to avoid false "0 vs N" mismatches for unusual article formats.
    if is_recommendation and requested_count is not None:
        from blogagent.tools.recommendation_extractor import (  # noqa: PLC0415
            extract_recommendations_from_article,
        )
        rich_recs = extract_recommendations_from_article(draft)
        actual_count = len(rich_recs) if rich_recs else count_recommendations(draft)
        quick_picks_in_draft = "Quick Picks" in draft
        if actual_count != requested_count:
            if actual_count == 0 and not quick_picks_in_draft:
                # No Quick Picks at all — missing_structure handles this below
                pass
            else:
                # Either Quick Picks exists with wrong count, or no bullets detected
                defects.append(
                    QualityDefect(
                        type="top_n_mismatch",
                        severity="high",
                        message=(
                            f"Topic requests {requested_count} items but article has "
                            f"{actual_count}. Fix to exactly {requested_count}."
                        ),
                        fixable=True,
                    )
                )
                score -= 20

    # --- 2. Quick Picks section missing (recommendation only) ---
    if is_recommendation and "Quick Picks" not in draft:
        defects.append(
            QualityDefect(
                type="missing_structure",
                severity="high",
                message="Recommendation article missing required '## Quick Picks' section.",
            )
        )
        score -= 15

    # --- 3. Repeated text warnings ---
    for w in warnings:
        if w.startswith("repeated-text:"):
            defects.append(
                QualityDefect(
                    type="repeated_text",
                    severity="medium",
                    message=w,
                )
            )
            score -= 10

    # --- 4. Weak source dominance ---
    if source_quality_scores:
        low_count = sum(1 for s in source_quality_scores if s.get("quality") == "low")
        total = len(source_quality_scores)
        if total > 0 and low_count / total > 0.6:
            severity: Literal["low", "medium", "high"] = "high" if is_recommendation else "medium"
            defects.append(
                QualityDefect(
                    type="weak_source_dominance",
                    severity=severity,
                    message=(
                        f"{low_count}/{total} sources are low quality (Quora/Reddit/social). "
                        "Prefer editorial or expert sources."
                    ),
                )
            )
            score -= 15

    # --- 5. Financial safety ---
    if is_financial:
        if not _has_financial_disclaimer(draft):
            defects.append(
                QualityDefect(
                    type="financial_safety",
                    severity="high",
                    message="Financial article missing 'not financial advice' disclaimer.",
                )
            )
            score -= 20
        if _has_direct_buy_sell_language(draft):
            defects.append(
                QualityDefect(
                    type="financial_safety",
                    severity="high",
                    message=(
                        "Article contains direct buy/sell language, which is not allowed "
                        "for financial topics."
                    ),
                )
            )
            score -= 20

    # --- 6. Article structure (title) ---
    if not _has_title(draft):
        defects.append(
            QualityDefect(
                type="seo_issue",
                severity="medium",
                message="Article missing H1 title (# Heading).",
            )
        )
        score -= 10

    # --- 7. Useful headings ---
    if not _has_useful_headings(draft):
        defects.append(
            QualityDefect(
                type="missing_structure",
                severity="low",
                message="Article has fewer than 2 section headings — structure is weak.",
            )
        )
        score -= 5

    # --- 8. Generic / placeholder output ---
    if _is_generic_output(draft):
        defects.append(
            QualityDefect(
                type="generic_output",
                severity="high",
                message="Article content appears placeholder-like or generic.",
            )
        )
        score -= 25

    # --- 9. Final Takeaway (recommendation) ---
    if is_recommendation and not re.search(r"Final Takeaway|## Takeaway", draft):
        defects.append(
            QualityDefect(
                type="missing_structure",
                severity="low",
                message="Recommendation article missing Final Takeaway section.",
            )
        )
        score -= 5

    score = max(0, score)

    # Revision required when any HIGH-severity defect exists.
    high_defects = [d for d in defects if d.severity == "high"]
    revision_required = len(high_defects) > 0

    # Cap score at 69 when high-severity defects exist — prevents a misleading
    # "score=90 passes=True" outcome when the article has a fundamental flaw.
    if high_defects:
        score = min(score, 69)

    passes = score >= 70 and not revision_required

    if not defects:
        summary = f"Score: {score}/100. No defects found."
    else:
        messages = "; ".join(d.message for d in defects[:3])
        more = f" (+{len(defects) - 3} more)" if len(defects) > 3 else ""
        summary = f"Score: {score}/100. {len(defects)} defect(s): {messages}{more}"

    return QualityEvaluationOutput(
        passes=passes,
        score=score,
        revision_required=revision_required,
        defects=defects,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Deterministic helpers
# ---------------------------------------------------------------------------

# Generic headings that are NOT individual recommendations
_GENERIC_HEADINGS: frozenset[str] = frozenset(
    {
        "how we chose",
        "how to choose",
        "methodology",
        "our methodology",
        "final takeaway",
        "takeaway",
        "conclusion",
        "introduction",
        "overview",
        "buying guide",
        "faqs",
        "frequently asked questions",
        "further reading",
        "sources",
        "references",
        "citations",
    }
)

# Source/reference section headings — strip these before counting
_SOURCE_SECTION_PATTERN = re.compile(
    r"\n#{1,3}\s*(?:Sources?|References?|Citations?|Further Reading)\s*\n",
    re.IGNORECASE,
)


def count_recommendations(markdown: str) -> int:
    """Count distinct recommendations in a markdown article.

    More robust than _count_quick_picks: handles bullet lists (- /*),
    numbered lists (1. /1)), and ignores source citation sections.

    Detection order:
      1. Quick Picks section — bullets or numbered items
      2. Numbered H2/H3 recommendation headings ("## 1. Best Perfume for…")
    """
    # Strip Sources / References section to avoid inflating count.
    no_sources = _SOURCE_SECTION_PATTERN.split(markdown)[0]

    # --- 1. Quick Picks section ---
    m = re.search(
        r"#{1,3}\s*Quick\s*Picks\s*\n(.*?)(?=\n#{1,3}|\Z)",
        no_sources,
        re.DOTALL | re.IGNORECASE,
    )
    if m:
        section = m.group(1)
        # Bullets: - item, * item
        bullets = re.findall(r"^\s*[-*]\s+\S", section, re.MULTILINE)
        # Numbered: 1. item, 1) item
        numbered = re.findall(r"^\s*\d+[.)]\s+\S", section, re.MULTILINE)
        count = len(bullets) + len(numbered)
        if count > 0:
            return count

    # --- 2. Numbered H2/H3 recommendation headings ---
    numbered_headings = re.findall(r"^#{2,3}\s+\d+[.)]\s+\S", no_sources, re.MULTILINE)
    if numbered_headings:
        return len(numbered_headings)

    return 0


def _count_quick_picks(draft: str) -> int:
    """Count bullet items in the Quick Picks section.

    Legacy helper kept for backward compatibility with existing tests.
    New code should call count_recommendations() instead.
    """
    m = re.search(r"##\s*Quick Picks\s*\n(.*?)(?=\n##|\Z)", draft, re.DOTALL)
    if not m:
        return 0
    section = m.group(1)
    bullets = re.findall(r"^\s*[-*]\s+.+", section, re.MULTILINE)
    return len(bullets)


def _is_evidence_limited_article(draft: str, actual_count: int, requested_count: int) -> bool:
    """Return True if the article explicitly explains a reduced count due to evidence limits.

    An evidence-limited reduction is acceptable when:
    - The article body explains that evidence only supported fewer items.
    - The title does not falsely claim the original requested_count.
    - The Quick Picks count matches actual_count (not requested_count).
    """
    lower = draft.lower()
    evidence_phrases = (
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
    )
    has_explanation = any(p in lower for p in evidence_phrases)

    # Title must not claim the wrong count.
    title_match = re.search(r"^#\s+(.+)", draft, re.MULTILINE)
    title = title_match.group(1).lower() if title_match else ""
    title_falsely_claims = f"top {requested_count}" in title or f"best {requested_count}" in title

    return has_explanation and not title_falsely_claims


def _has_financial_disclaimer(draft: str) -> bool:
    lower = draft.lower()
    return (
        "not financial advice" in lower
        or "not constitute financial advice" in lower
        or "educational purposes only" in lower
        or "consult a qualified financial" in lower
    )


def _has_direct_buy_sell_language(draft: str) -> bool:
    lower = draft.lower()
    patterns = [
        r"\bbuy this stock\b",
        r"\binvest in .{1,30} now\b",
        r"\bguaranteed returns?\b",
        r"\bsell .{1,20} now\b",
    ]
    return any(re.search(p, lower) for p in patterns)


def _has_title(draft: str) -> bool:
    return bool(re.search(r"^#\s+\S", draft, re.MULTILINE))


def _has_useful_headings(draft: str) -> bool:
    headings = re.findall(r"^#{2,}\s+\S", draft, re.MULTILINE)
    return len(headings) >= 2


def _is_generic_output(draft: str) -> bool:
    """True if the draft is placeholder-like rather than substantive."""
    placeholder_patterns = [
        r"\[Placeholder",
        r"\[INSERT",
        r"\[TODO",
        r"lorem ipsum",
        r"Lorem ipsum",
    ]
    lower = draft.lower()
    if any(re.search(p, draft) for p in placeholder_patterns):
        return True
    # A draft shorter than 100 chars is almost certainly empty/placeholder.
    if len(draft.strip()) < 100:
        return True
    # Warn if draft has almost no alpha content (fewer than 50 alpha chars total).
    if len(re.findall(r"[a-zA-Z]", lower)) < 50:
        return True
    return False
