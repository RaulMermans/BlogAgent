"""Article Quality Gate — deterministic editorial quality checks.

Permission class: read_only
All operations are deterministic — no LLM calls.

Checks the FINAL article (after revision and polish) for:
- Internal pipeline language that should not appear in published articles
- Structural quality issues (repeated paragraphs, malformed headings)
- Recommendation differentiation (distinct Best-for per pick)
- Human readability heuristics

A score below 80 blocks publish_ready status.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Internal pipeline phrases that must never appear in consumer-facing articles
# ---------------------------------------------------------------------------

_PIPELINE_PHRASES: tuple[str, ...] = (
    "query contract",
    "candidate pack",
    "evidence table",
    "locked candidates",
    "not explicitly mentioned in the evidence",
    "not explicitly mentioned in evidence",
    "source: not explicitly mentioned",
    "provided source excerpts",
    "evidence-limited mode",
    "candidate_id",
    "allowed recommendations",
    "rejected candidates",
    "recommendation_strictness",
    "entity_subtype",
    "evidence_mode",
    "source_quality",
    "source_type",
    "candidate_basis",
    "evidence_score",
    "clean_name_score",
)

# Generic intro phrases that inflate length without adding value
_GENERIC_INTRO_PHRASES: tuple[str, ...] = (
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
)

# Malformed heading patterns
_MALFORMED_HEADING_RE = re.compile(
    r"^#{2,3}\s+(?:"
    r"https?://|"  # URL as heading
    r"\$\d+|"  # Price as heading
    r"\d{4}-\d{2}|"  # Date as heading
    r"[A-Z][a-z]+\s+\d{4}"  # Month Year as heading
    r")",
    re.MULTILINE,
)

_SOURCE_SECTION_RE = re.compile(
    r"\n#{1,3}\s*(?:Sources?|References?|Citations?|Further Reading)\s*\n",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------


class ArticleQualityDefect(BaseModel):
    type: str
    severity: Literal["low", "medium", "high"]
    message: str
    fixable: bool = True


class ArticleQualityGateResult(BaseModel):
    score: int  # 0–100
    passes: bool
    defects: list[ArticleQualityDefect] = Field(default_factory=list)
    polish_required: bool
    publish_ceiling: Literal[
        "publish_ready",
        "publish_ready_with_editorial_review",
        "draft_only_not_publish_ready",
    ]
    summary: str


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_article_quality_gate(
    article_markdown: str,
    is_recommendation: bool,
    requested_count: int | None = None,
    candidate_pack: dict | None = None,
) -> ArticleQualityGateResult:
    """Run deterministic editorial quality gate on the final article."""
    defects: list[ArticleQualityDefect] = []
    score = 100
    lower = article_markdown.lower()

    # --- 1. Internal pipeline language ---
    pipeline_hits = [p for p in _PIPELINE_PHRASES if p in lower]
    if pipeline_hits:
        # High severity only if more than 1 hit (a single mention might be fine in editorial notes)
        severity: Literal["low", "medium", "high"] = "high" if len(pipeline_hits) >= 2 else "medium"
        defects.append(
            ArticleQualityDefect(
                type="pipeline_language",
                severity=severity,
                message=(
                    f"Article contains {len(pipeline_hits)} internal pipeline phrase(s) "
                    f"that must be removed before use: "
                    + ", ".join(f'"{p}"' for p in pipeline_hits[:3])
                ),
                fixable=True,
            )
        )
        score -= 25 if severity == "high" else 12

    # --- 2. Malformed headings ---
    bad_headings = _MALFORMED_HEADING_RE.findall(article_markdown)
    if bad_headings:
        defects.append(
            ArticleQualityDefect(
                type="malformed_heading",
                severity="high",
                message=(
                    f"{len(bad_headings)} heading(s) contain URL, price, or date debris: "
                    + str(bad_headings[:2])
                ),
                fixable=True,
            )
        )
        score -= 20

    # --- 3. "Source: Not explicitly mentioned" lines ---
    source_not_mentioned = re.findall(
        r"[*_]*Source[*_]*:\s*[Nn]ot\s+explicitly\s+mentioned", article_markdown
    )
    if source_not_mentioned:
        defects.append(
            ArticleQualityDefect(
                type="pipeline_language",
                severity="high",
                message=(
                    f"Article has {len(source_not_mentioned)} 'Source: Not explicitly mentioned' "
                    "line(s). These are internal pipeline notes and must be removed."
                ),
                fixable=True,
            )
        )
        score -= 20

    # --- 4. Repeated paragraphs ---
    repeated = _find_repeated_paragraphs(article_markdown)
    if repeated:
        defects.append(
            ArticleQualityDefect(
                type="repeated_paragraph",
                severity="medium",
                message=(
                    f"{len(repeated)} paragraph(s) appear more than once in the article. "
                    "Remove or rewrite duplicates."
                ),
                fixable=True,
            )
        )
        score -= 12

    # --- 5. Generic filler intro ---
    # Flag when the intro is heavily clichéd (>=3 stock phrases regardless of length)
    # or moderately clichéd AND long (>=2 phrases and over 120 words).
    intro = _extract_intro(article_markdown)
    intro_words = len(intro.split())
    intro_lower = intro.lower()
    generic_intro_count = sum(1 for p in _GENERIC_INTRO_PHRASES if p in intro_lower)
    if generic_intro_count >= 3 or (generic_intro_count >= 2 and intro_words > 120):
        defects.append(
            ArticleQualityDefect(
                type="generic_intro",
                severity="medium",
                message=(
                    f"Intro is {intro_words} words and uses {generic_intro_count} generic "
                    "opener phrase(s). Open with a specific observation instead."
                ),
                fixable=True,
            )
        )
        score -= 10

    # --- 6. Heading longer than 90 characters ---
    long_headings = [
        h for h in re.findall(r"^#{2,3}\s+(.+)$", article_markdown, re.MULTILINE) if len(h) > 90
    ]
    if long_headings:
        defects.append(
            ArticleQualityDefect(
                type="long_heading",
                severity="low",
                message=(
                    f"{len(long_headings)} section heading(s) exceed 90 characters. "
                    "Shorten for readability."
                ),
                fixable=True,
            )
        )
        score -= 5

    # --- 7. Recommendation differentiation (recommendation articles only) ---
    if is_recommendation:
        best_for_matches = re.findall(
            r"\*\*Best for[:\*]+\*?\*?\s*([^\n]{5,80})", article_markdown, re.IGNORECASE
        )
        rec_sections = _count_recommendation_sections(article_markdown)

        if rec_sections > 0:
            # At least 70% of recommendation sections should have "Best for"
            coverage = len(best_for_matches) / rec_sections
            if coverage < 0.7:
                defects.append(
                    ArticleQualityDefect(
                        type="missing_best_for",
                        severity="medium",
                        message=(
                            f"Only {len(best_for_matches)}/{rec_sections} recommendation "
                            "sections have a 'Best for' entry. Add one per pick."
                        ),
                        fixable=True,
                    )
                )
                score -= 10

            # Check for duplicate "Best for" descriptions
            unique_best_for = {b.lower().strip() for b in best_for_matches}
            if len(best_for_matches) > 1 and len(unique_best_for) < len(best_for_matches):
                defects.append(
                    ArticleQualityDefect(
                        type="duplicate_best_for",
                        severity="medium",
                        message=(
                            "Multiple picks share the same 'Best for' description. "
                            "Each pick needs a distinct use case."
                        ),
                        fixable=True,
                    )
                )
                score -= 8

        # Quick Picks section present check
        if "Quick Picks" not in article_markdown:
            defects.append(
                ArticleQualityDefect(
                    type="missing_quick_picks",
                    severity="high",
                    message="Recommendation article is missing the 'Quick Picks' section.",
                    fixable=False,
                )
            )
            score -= 25

        # Count check
        if requested_count is not None:
            qp_count = _count_quick_picks(article_markdown)
            if qp_count > 0 and qp_count != requested_count:
                # Natural narrowing-framing check — the article should explain a reduced
                # count in plain language (either pipeline-style "evidence supported" framing
                # or natural editorial framing like "stood out", "narrowed this to", etc.)
                lower_art = article_markdown.lower()
                has_narrowing_framing = any(
                    p in lower_art
                    for p in (
                        "available evidence supported",
                        "evidence supported",
                        "sources supported only",
                        "rather than the",
                        "stood out",
                        "narrowed this to",
                        "narrowed the list",
                        "after reviewing",
                        "we focused on",
                        "we settled on",
                        "made the cut",
                        "didn't make the list",
                        "could not find enough",
                        "couldn't find enough",
                    )
                )
                if not has_narrowing_framing:
                    defects.append(
                        ArticleQualityDefect(
                            type="count_mismatch",
                            severity="high",
                            message=(
                                f"Quick Picks has {qp_count} items but {requested_count} "
                                "were requested. Add a natural sentence explaining the "
                                "narrower focus, or fix the count."
                            ),
                            fixable=True,
                        )
                    )
                    score -= 20

    score = max(0, min(100, score))

    high_defects = [d for d in defects if d.severity == "high"]
    medium_defects = [d for d in defects if d.severity == "medium"]
    polish_required = score < 80 or len(high_defects) > 0 or len(medium_defects) >= 2

    if high_defects:
        score = min(score, 69)
        publish_ceiling: Literal[
            "publish_ready",
            "publish_ready_with_editorial_review",
            "draft_only_not_publish_ready",
        ] = "draft_only_not_publish_ready"
    elif medium_defects or score < 80:
        publish_ceiling = "publish_ready_with_editorial_review"
    else:
        publish_ceiling = "publish_ready"

    passes = score >= 80 and not high_defects

    if not defects:
        summary = f"Score: {score}/100. Article passes quality gate."
    else:
        msgs = "; ".join(d.message[:80] for d in defects[:3])
        more = f" (+{len(defects) - 3} more)" if len(defects) > 3 else ""
        summary = f"Score: {score}/100. {len(defects)} issue(s): {msgs}{more}"

    return ArticleQualityGateResult(
        score=score,
        passes=passes,
        defects=defects,
        polish_required=polish_required,
        publish_ceiling=publish_ceiling,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_intro(markdown: str) -> str:
    """Extract text between H1 and first H2."""
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
    return " ".join(intro_lines)


def _find_repeated_paragraphs(markdown: str) -> list[str]:
    """Find paragraphs that appear more than once in the article."""
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


def _count_recommendation_sections(markdown: str) -> int:
    """Count numbered H2/H3 recommendation sections."""
    no_sources = _SOURCE_SECTION_RE.split(markdown)[0]
    numbered = re.findall(r"^#{2,3}\s+\d+[.)]\s+\S", no_sources, re.MULTILINE)
    return len(numbered)


def _count_quick_picks(markdown: str) -> int:
    """Count items in Quick Picks section."""
    no_sources = _SOURCE_SECTION_RE.split(markdown)[0]
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
