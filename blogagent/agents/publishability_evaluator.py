"""Publishability Evaluator — determines if an article is ready to publish.

Permission class: read_only

Evaluates whether the draft meets personal-blog publish standards using
deterministic heuristics plus optional LLM judgment (when
BLOGAGENT_USE_LLM_EDITOR=true).

Output: PublishabilityEvaluation with a score, defect list, and polish flag.
"""

from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel

PublishabilityDefectType = Literal[
    "generic_voice",
    "weak_pov",
    "thin_recommendations",
    "weak_sensory_detail",
    "poor_source_synthesis",
    "weak_intro",
    "weak_conclusion",
    "seo_issue",
    "thin_article",
    "unmet_requested_count",
    "weak_evidence_limited_framing",
    "insufficient_recommendation_depth",
    "missing_product_context",
    "generic_seo_voice",
    "structural_defect",
]

DefectSeverity = Literal["low", "medium", "high"]


class PublishabilityDefect(BaseModel):
    type: PublishabilityDefectType
    severity: DefectSeverity
    message: str


class PublishabilityEvaluation(BaseModel):
    publish_ready: bool
    score: int  # 0-100
    polish_required: bool
    defects: list[PublishabilityDefect]
    summary: str


# ---------------------------------------------------------------------------
# Generic/content-mill phrases that signal low editorial quality
# ---------------------------------------------------------------------------

_GENERIC_INTRO_PHRASES = (
    "in the world of",
    "in today's world",
    "in this article, we will",
    "in this blog post, we will",
    "are you looking for",
    "look no further",
    "welcome to",
    "this article will cover",
    "this guide will help you",
    "whether you're a",
    "have you ever wondered",
    "it's no secret that",
    "without further ado",
    "when it comes to",
    "in today's competitive",
    "in recent years",
    "in an ever-changing",
)

_CONTENT_MILL_PHRASES = (
    "look no further",
    "we've got you covered",
    "comprehensive guide",
    "complete guide",
    "ultimate guide",
    "everything you need to know",
    "dive right in",
    "let's dive in",
    "let's get started",
    "without further ado",
    "stay tuned",
    "keep reading to find out",
    "at the end of the day",
    "without a doubt",
    "needless to say",
)

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

_LIFESTYLE_CONTEXT_TERMS = (
    "date night",
    "occasion",
    "mood",
    "season",
    "style",
    "aesthetic",
    "layering",
    "occasion",
    "wardrobe",
    "identity",
    "vibe",
)

# Structural defects that must prevent a perfect (100) score regardless of how
# strong the prose otherwise reads — these are hard quality-floor checks, not
# stylistic nitpicks. (Mirrors the structural checks in article_quality_gate,
# kept independent so each module can be tested and evolve on its own.)
_MALFORMED_HEADING_RE = re.compile(
    r"^#{2,3}\s+(?:"
    r"https?://|"  # URL as heading
    r"\$\d+|"  # Price as heading
    r"\d{4}-\d{2}|"  # Date as heading
    r"[A-Z][a-z]+\s+\d{4}"  # Month Year as heading
    r")",
    re.MULTILINE,
)

_SOURCE_NOT_MENTIONED_RE = re.compile(r"[*_]*Source[*_]*:\s*[Nn]ot\s+explicitly\s+mentioned")

_SOURCE_SECTION_RE = re.compile(
    r"\n#{1,3}\s*(?:Sources?|References?|Citations?|Further Reading)\s*\n",
    re.IGNORECASE,
)

_WEAK_CONCLUSION_PHRASES = (
    "in conclusion",
    "to summarize",
    "to sum up",
    "in summary",
    "as you can see",
    "hopefully this article",
    "we hope this guide",
    "now that you know",
)


def evaluate_publishability(
    article_markdown: str,
    topic: str,
    is_recommendation: bool,
    selected_skills: list[str],
    source_quality_scores: list[dict],
    evidence_sufficiency: Optional[dict] = None,
    requested_count: Optional[int] = None,
    actual_recommendation_count: Optional[int] = None,
) -> PublishabilityEvaluation:
    """Run deterministic publishability checks on the article."""
    defects: list[PublishabilityDefect] = []
    score = 100
    lower = article_markdown.lower()
    topic_lower = topic.lower()

    is_fragrance = any(
        kw in topic_lower for kw in ("perfume", "parfum", "fragrance", "cologne", "scent", "eau de")
    )
    is_lifestyle = any(
        kw in topic_lower
        for kw in ("beauty", "fashion", "lifestyle", "fragrance", "makeup", "skincare", "perfume")
    )

    # --- 0. Structural integrity — a perfect score is impossible with these present ---
    # These are hard quality-floor defects (malformed headings, repeated paragraphs,
    # leaked "Source: Not explicitly mentioned" pipeline notes). No amount of strong
    # voice or sensory detail should let an article with these score 100.
    structural_issues: list[str] = []
    bad_headings = _MALFORMED_HEADING_RE.findall(article_markdown)
    if bad_headings:
        structural_issues.append(
            f"{len(bad_headings)} heading(s) contain URL, price, or date debris"
        )
    repeated_paragraphs = _find_repeated_paragraphs(article_markdown)
    if repeated_paragraphs:
        structural_issues.append(f"{len(repeated_paragraphs)} paragraph(s) repeat verbatim")
    not_mentioned = _SOURCE_NOT_MENTIONED_RE.findall(article_markdown)
    if not_mentioned:
        structural_issues.append(
            f"{len(not_mentioned)} 'Source: Not explicitly mentioned' line(s) leaked through"
        )
    broken_quotes = _find_broken_quotes(article_markdown)
    if broken_quotes:
        structural_issues.append(
            f"{len(broken_quotes)} paragraph(s) contain an unclosed quotation mark "
            "(likely a truncated source quote)"
        )
    if structural_issues:
        defects.append(
            PublishabilityDefect(
                type="structural_defect",
                severity="high",
                message=(
                    "Structural defects make a perfect score impossible: "
                    + "; ".join(structural_issues)
                    + ". Fix these before considering the article publish-ready."
                ),
            )
        )
        score -= 30

    # --- 1. Generic intro check ---
    intro = _extract_intro(article_markdown)
    intro_lower = intro.lower()
    generic_intro_count = sum(1 for p in _GENERIC_INTRO_PHRASES if p in intro_lower)
    if generic_intro_count >= 2:
        defects.append(
            PublishabilityDefect(
                type="generic_voice",
                severity="high",
                message=(
                    f"Intro uses {generic_intro_count} generic filler phrase(s). "
                    "Open with a specific observation, question, or editorial thesis instead."
                ),
            )
        )
        score -= 20
    elif generic_intro_count == 1:
        defects.append(
            PublishabilityDefect(
                type="weak_intro",
                severity="medium",
                message=(
                    "Intro contains generic opening phrase. Strengthen with editorial specificity."
                ),
            )
        )
        score -= 8

    # --- 2. Content-mill phrasing ---
    mill_count = sum(1 for p in _CONTENT_MILL_PHRASES if p in lower)
    if mill_count >= 3:
        defects.append(
            PublishabilityDefect(
                type="generic_voice",
                severity="medium",
                message=(
                    f"Article contains {mill_count} content-mill phrases "
                    "(e.g. 'look no further', 'comprehensive guide'). "
                    "Replace with specific, editorial language."
                ),
            )
        )
        score -= 10
    elif mill_count >= 1:
        defects.append(
            PublishabilityDefect(
                type="generic_voice",
                severity="low",
                message=(
                    f"Article contains {mill_count} generic/filler phrase(s). Consider removing."
                ),
            )
        )
        score -= 4

    # --- 3. Editorial POV / thesis ---
    has_pov = _has_editorial_pov(article_markdown)
    if not has_pov:
        defects.append(
            PublishabilityDefect(
                type="weak_pov",
                severity="medium",
                message=(
                    "Article lacks a clear editorial thesis or opinion. "
                    "Add a specific point of view in the intro or throughout."
                ),
            )
        )
        score -= 12

    # --- 4. Unmet requested count ---
    if is_recommendation and requested_count is not None:
        from blogagent.agents.quality_evaluator import (  # noqa: PLC0415
            _is_evidence_limited_article,
            count_recommendations,
        )

        actual = actual_recommendation_count
        if actual is None:
            actual = count_recommendations(article_markdown)
        if actual < requested_count:
            has_explanation = _is_evidence_limited_article(
                article_markdown, actual, requested_count
            )
            if has_explanation and actual >= 3:
                defects.append(
                    PublishabilityDefect(
                        type="weak_evidence_limited_framing",
                        severity="low",
                        message=(
                            f"Article has {actual} of {requested_count} requested items. "
                            "Evidence-limited framing present — verify it is clearly worded."
                        ),
                    )
                )
                score -= 5
            else:
                defects.append(
                    PublishabilityDefect(
                        type="unmet_requested_count",
                        severity="high",
                        message=(
                            f"Topic requests {requested_count} items but article has {actual}. "
                            "Add evidence-limited framing or additional recommendations."
                        ),
                    )
                )
                score -= 25

    # --- 5. Recommendation depth (recommendation topics) ---
    if is_recommendation:
        thin_recs = _check_thin_recommendations(article_markdown)
        if thin_recs:
            defects.append(
                PublishabilityDefect(
                    type="thin_recommendations",
                    severity="high",
                    message=thin_recs,
                )
            )
            score -= 20

    # --- 6. Fragrance sensory detail ---
    # Sensory/note language is only expected when the article is recommending
    # specific fragrance products. A fragrance how-to/explainer doesn't describe
    # specific scents and shouldn't be penalized for lacking note terminology.
    if is_fragrance and is_recommendation:
        sensory_count = sum(1 for t in _FRAGRANCE_SENSORY_TERMS if t in lower)
        lifestyle_count = sum(1 for t in _LIFESTYLE_CONTEXT_TERMS if t in lower)
        if sensory_count < 3:
            defects.append(
                PublishabilityDefect(
                    type="weak_sensory_detail",
                    severity="high",
                    message=(
                        f"Fragrance article mentions only {sensory_count} sensory/note term(s). "
                        "Include scent families, notes (top/heart/base), or mood descriptions "
                        "where evidence supports them."
                    ),
                )
            )
            score -= 18
        elif sensory_count < 6:
            defects.append(
                PublishabilityDefect(
                    type="weak_sensory_detail",
                    severity="medium",
                    message=(
                        f"Fragrance article mentions {sensory_count} sensory terms — "
                        "could include more context (occasion, scent family, projection)."
                    ),
                )
            )
            score -= 8
        if lifestyle_count < 2 and is_lifestyle:
            defects.append(
                PublishabilityDefect(
                    type="weak_sensory_detail",
                    severity="low",
                    message=(
                        "Lifestyle/beauty article could include more occasion or mood context "
                        "(e.g. 'date night', 'season', 'vibe')."
                    ),
                )
            )
            score -= 5

    # --- 6. Lifestyle/beauty editorial depth ---
    elif is_lifestyle and is_recommendation:
        lifestyle_count = sum(1 for t in _LIFESTYLE_CONTEXT_TERMS if t in lower)
        if lifestyle_count < 2:
            defects.append(
                PublishabilityDefect(
                    type="thin_recommendations",
                    severity="medium",
                    message=(
                        "Lifestyle recommendation article lacks occasion/mood/context detail. "
                        "Connect product choices to mood, styling, or identity."
                    ),
                )
            )
            score -= 10

    # --- 7. Source synthesis (not just list) ---
    if not _has_source_synthesis(article_markdown, source_quality_scores):
        defects.append(
            PublishabilityDefect(
                type="poor_source_synthesis",
                severity="low",
                message=(
                    "Sources appear listed rather than synthesised. "
                    "Weave source insights into prose for better editorial authority."
                ),
            )
        )
        score -= 6

    # --- 8. Weak conclusion ---
    conclusion = _extract_conclusion(article_markdown)
    if conclusion:
        concl_lower = conclusion.lower()
        weak_concl_count = sum(1 for p in _WEAK_CONCLUSION_PHRASES if p in concl_lower)
        if weak_concl_count >= 1 or len(conclusion.strip()) < 80:
            defects.append(
                PublishabilityDefect(
                    type="weak_conclusion",
                    severity="low",
                    message=(
                        "Conclusion is generic or too short. "
                        "End with an editorial recommendation or memorable insight."
                    ),
                )
            )
            score -= 5

    # --- 9. Title quality ---
    title_match = re.search(r"^#\s+(.+)", article_markdown, re.MULTILINE)
    if title_match:
        title_text = title_match.group(1).lower()
        generic_title_words = {"guide", "everything", "ultimate", "complete", "comprehensive"}
        if any(w in title_text for w in generic_title_words):
            defects.append(
                PublishabilityDefect(
                    type="seo_issue",
                    severity="low",
                    message=(
                        "Title uses generic SEO filler words "
                        "(e.g. 'ultimate guide', 'everything'). "
                        "Use a specific, editorial title instead."
                    ),
                )
            )
            score -= 4

    score = max(0, min(100, score))

    high_defects = [d for d in defects if d.severity == "high"]
    medium_defects = [d for d in defects if d.severity == "medium"]

    # Core domain dimensions that always require polish when defective:
    # - weak_sensory_detail for fragrance posts
    # - unmet_requested_count
    # - thin_recommendations
    # - weak_pov
    _CORE_DEFECT_TYPES = {
        "weak_sensory_detail",
        "unmet_requested_count",
        "thin_recommendations",
        "weak_pov",
    }
    has_core_medium = any(d.type in _CORE_DEFECT_TYPES for d in medium_defects)
    polish_required = (
        score < 80 or len(high_defects) > 0 or len(medium_defects) >= 2 or has_core_medium
    )

    # Advisory publish_ready (stricter than before; publish_contract is the final truth)
    publish_ready = score >= 75 and len(high_defects) == 0

    if not defects:
        summary = f"Score: {score}/100. Article meets publish standards."
    else:
        msgs = "; ".join(d.message[:80] for d in defects[:3])
        more = f" (+{len(defects) - 3} more)" if len(defects) > 3 else ""
        summary = f"Score: {score}/100. {len(defects)} issue(s): {msgs}{more}"

    return PublishabilityEvaluation(
        publish_ready=publish_ready,
        score=score,
        polish_required=polish_required,
        defects=defects,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_broken_quotes(markdown: str) -> list[str]:
    """Find paragraphs with an unmatched quotation mark.

    An odd number of straight double-quotes, or a mismatched count of opening
    vs. closing smart quotes, usually means a source quote was truncated when
    copied into the draft (e.g. a quote that opens but never closes).
    """
    no_sources = _SOURCE_SECTION_RE.split(markdown)[0]
    broken: list[str] = []
    for para in re.split(r"\n\n+", no_sources):
        para = para.strip()
        if not para or para.startswith("#"):
            continue
        straight = para.count('"')
        opening_smart = para.count("“")
        closing_smart = para.count("”")
        if straight % 2 == 1 or opening_smart != closing_smart:
            broken.append(para[:80])
    return broken


def _find_repeated_paragraphs(markdown: str) -> list[str]:
    """Find paragraphs (outside the sources section) that appear more than once."""
    no_sources = _SOURCE_SECTION_RE.split(markdown)[0]
    paragraphs = [
        p.strip()
        for p in re.split(r"\n\n+", no_sources)
        if len(p.strip()) > 60 and not p.strip().startswith("#")
    ]
    seen: dict[str, int] = {}
    repeated: list[str] = []
    for para in paragraphs:
        key = re.sub(r"\s+", " ", para.lower())
        seen[key] = seen.get(key, 0) + 1
        if seen[key] == 2:
            repeated.append(para[:80])
    return repeated


def _extract_intro(markdown: str) -> str:
    """Extract the first paragraph after the H1 title (up to ~300 chars)."""
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


def _extract_conclusion(markdown: str) -> str:
    """Extract the last section content."""
    # Find Final Takeaway or Conclusion section
    m = re.search(
        r"#{1,3}\s*(?:Final Takeaway|Conclusion|Takeaway|Closing Thoughts)"
        r"\s*\n(.*?)(?=\n#{1,3}|\Z)",
        markdown,
        re.DOTALL | re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()
    # Fall back to last 200 chars of the article
    return markdown.strip()[-200:]


def _has_editorial_pov(markdown: str) -> bool:
    """Check for editorial opinion signals in the article."""
    lower = markdown.lower()
    pov_signals = (
        # Opinion/judgment words
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
        "we prefer",
        "the winner",
        "our favorite",
        "surprisingly",
        "underrated",
        "overrated",
        "don't",
        "shouldn't",
        "you should",
        "the real",
    )
    return sum(1 for s in pov_signals if s in lower) >= 2


def _check_thin_recommendations(markdown: str) -> str:
    """Check if recommendation items have enough detail. Returns error message or ''."""
    # Look for recommendation entries — each should have at least a "best for" or "why"
    rec_sections = re.findall(
        r"(?:\*\*Best for\*\*|\*\*Why|Best for:|Why it works:|Caveat:)",
        markdown,
        re.IGNORECASE,
    )
    # Count Quick Picks items
    qp_match = re.search(
        r"#{1,3}\s*Quick\s*Picks\s*\n(.*?)(?=\n#{1,3}|\Z)",
        markdown,
        re.DOTALL | re.IGNORECASE,
    )
    if qp_match:
        bullets = re.findall(r"^\s*[-*]\s+\S", qp_match.group(1), re.MULTILINE)
        numbered = re.findall(r"^\s*\d+[.)]\s+\S", qp_match.group(1), re.MULTILINE)
        picks_count = len(bullets) + len(numbered)
        if picks_count > 0 and len(rec_sections) < picks_count // 2:
            return (
                f"Recommendation article has {picks_count} picks but only "
                f"{len(rec_sections)} detail section(s). "
                "Each pick needs a clear use case, rationale, and source citation."
            )
    return ""


def _has_source_synthesis(markdown: str, source_quality_scores: list[dict]) -> bool:
    """Check that sources are cited in prose (not just listed)."""
    # Look for inline citations like [title](url)
    inline_citations = re.findall(r"\[.+?\]\(https?://", markdown)
    return len(inline_citations) >= 1
