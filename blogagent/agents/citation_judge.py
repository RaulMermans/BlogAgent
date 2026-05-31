"""citation_judge — optional LLM-backed semantic citation verification.

Permission class: read_only

When BLOGAGENT_USE_LLM_CITATION_JUDGE=true and a source excerpt is available,
calls generate_structured() to judge whether the excerpt supports the claim.

Falls back to a deterministic keyword-overlap heuristic on any provider failure.
Never crashes due to provider errors.
Never uses outside knowledge — judges only the provided excerpt.
"""

from __future__ import annotations

import logging
import os

from blogagent.agents.prompts import CITATION_JUDGE_PROMPT
from blogagent.llm.client import generate_structured
from blogagent.llm.schemas import CitationJudgmentOutput

logger = logging.getLogger(__name__)

_MAX_EXCERPT_CHARS = 2000

_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "of",
        "in",
        "on",
        "at",
        "to",
        "for",
        "and",
        "or",
        "but",
        "not",
        "that",
        "this",
        "these",
        "those",
        "it",
        "its",
        "by",
        "from",
        "with",
        "as",
        "which",
        "who",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
    }
)


def judge_citation_support(
    claim: str,
    source_excerpt: str,
    source_url: str,
) -> CitationJudgmentOutput:
    """Determine whether source_excerpt supports claim.

    Behavior depends on BLOGAGENT_USE_LLM_CITATION_JUDGE (default: false):
    - false → deterministic keyword-overlap heuristic (always safe, free)
    - true  → LLM call via generate_structured(); falls back to heuristic on failure
    """
    use_llm = os.getenv("BLOGAGENT_USE_LLM_CITATION_JUDGE", "false").strip().lower() == "true"

    if not use_llm:
        return _deterministic_judge(claim, source_excerpt, source_url)

    return _llm_judge(claim, source_excerpt, source_url)


# ---------------------------------------------------------------------------
# LLM path
# ---------------------------------------------------------------------------


def _llm_judge(claim: str, source_excerpt: str, source_url: str) -> CitationJudgmentOutput:
    user_prompt = CITATION_JUDGE_PROMPT.format(
        claim=claim,
        source_url=source_url,
        source_excerpt=source_excerpt[:_MAX_EXCERPT_CHARS],
    )
    result = generate_structured(
        system_prompt="You are a citation judge. Return only the JSON response.",
        user_prompt=user_prompt,
        output_model=CitationJudgmentOutput,
        temperature=0.0,
    )

    if result.data is None or result.error:
        warning = result.error or result.warning or "LLM citation judge returned no data"
        logger.warning("LLM citation judge failed, using deterministic fallback: %s", warning)
        fallback = _deterministic_judge(claim, source_excerpt, source_url)
        return CitationJudgmentOutput(
            claim=fallback.claim,
            support_status=fallback.support_status,
            confidence=fallback.confidence,
            explanation=f"[LLM fallback: {warning}] {fallback.explanation}",
        )

    return result.data


# ---------------------------------------------------------------------------
# Deterministic fallback
# ---------------------------------------------------------------------------


def _deterministic_judge(
    claim: str,
    source_excerpt: str,
    source_url: str,
) -> CitationJudgmentOutput:
    """Keyword-overlap heuristic. Always deterministic; never uses outside knowledge."""
    if not source_excerpt or not source_excerpt.strip():
        return CitationJudgmentOutput(
            claim=claim,
            support_status="unsupported",
            confidence="high",
            explanation="No source excerpt available to verify claim.",
        )

    claim_words = {w.lower() for w in claim.split()} - _STOPWORDS
    excerpt_words = {w.lower() for w in source_excerpt.split()} - _STOPWORDS

    if not claim_words:
        return CitationJudgmentOutput(
            claim=claim,
            support_status="unsupported",
            confidence="low",
            explanation="Claim has no meaningful keywords to match against source.",
        )

    overlap = len(claim_words & excerpt_words) / len(claim_words)

    if overlap >= 0.5:
        return CitationJudgmentOutput(
            claim=claim,
            support_status="supported",
            confidence="low",
            explanation=(
                f"Deterministic keyword overlap {overlap:.0%} — "
                "heuristic only; semantic verification not performed."
            ),
        )
    if overlap >= 0.2:
        return CitationJudgmentOutput(
            claim=claim,
            support_status="partially_supported",
            confidence="low",
            explanation=(
                f"Partial keyword overlap {overlap:.0%} — "
                "heuristic only; semantic verification not performed."
            ),
        )
    return CitationJudgmentOutput(
        claim=claim,
        support_status="unsupported",
        confidence="low",
        explanation=(
            f"Insufficient keyword overlap {overlap:.0%} — "
            "heuristic only; semantic verification not performed."
        ),
    )
