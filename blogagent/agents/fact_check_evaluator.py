"""Fact-Check Evaluator — claim extraction and citation evaluation.

evaluate_draft() checks BLOGAGENT_USE_LLM_FACTCHECK:
  false (default) → deterministic judgment from citation_matches; no API call.
  true            → calls the LLM client for richer judgment; falls back to
                    deterministic logic if the call fails.

Returns LLMResult so callers can inspect configured_provider, actual provider,
is_mock, and any fallback warning.

The evaluator never invents sources. It judges only against the provided
claims, citation matches, and source scores.
"""

from __future__ import annotations

import logging
import os

from blogagent.agents import prompts
from blogagent.llm import client as llm_client
from blogagent.llm.schemas import FactCheckJudgmentOutput, LLMResult
from blogagent.workflow.state import (
    CitationMatch,
    CitationStatus,
    ClaimImportance,
    SourceScore,
)

logger = logging.getLogger(__name__)

_MOCK_MODEL = "mock-1.0"
_MOCK_PROVIDER = "mock"


def _use_llm() -> bool:
    return os.getenv("BLOGAGENT_USE_LLM_FACTCHECK", "false").strip().lower() == "true"


def evaluate_draft(
    topic: str,
    draft: str,
    claims: list,
    citation_matches: list[CitationMatch],
    source_scores: list[SourceScore],
) -> LLMResult:
    """Return LLMResult whose .data is a FactCheckJudgmentOutput.

    In deterministic mode, derives judgment purely from citation_matches.
    Unsupported high-importance claims always produce a blocking issue.
    """
    if not _use_llm():
        judgment = _deterministic_judgment(citation_matches)
        return LLMResult(
            data=judgment,
            provider=_MOCK_PROVIDER,
            model=_MOCK_MODEL,
            is_mock=True,
            configured_provider="mock",
        )

    # Build a compact summary of claims and citation status for the LLM prompt.
    claim_summary = _format_claim_summary(claims, citation_matches)
    source_summary = _format_source_summary(source_scores)
    configured_provider = os.getenv("BLOGAGENT_LLM_PROVIDER", "mock").strip().lower()

    result = llm_client.generate_structured(
        system_prompt=prompts.FACT_CHECK_JUDGMENT_PROMPT.format(
            topic=topic,
            draft=draft[:3000],  # cap to avoid huge prompts
            claim_summary=claim_summary,
            source_summary=source_summary,
        ),
        user_prompt=(
            "Evaluate the draft and return a JSON judgment with: "
            "passed, revision_required, blocking_issues, revision_notes, confidence."
        ),
        output_model=FactCheckJudgmentOutput,
    )

    if result.is_mock or result.data is None:
        # LLM fell back to mock; use deterministic judgment with topic-specific logic.
        judgment = _deterministic_judgment(citation_matches)
        fallback_warning = result.warning or (
            f"LLM fact-check failed: {result.error}" if result.error else None
        )
        logger.warning("LLM fact-check fell back to deterministic: %s", fallback_warning)
        return LLMResult(
            data=judgment,
            provider=_MOCK_PROVIDER,
            model=_MOCK_MODEL,
            is_mock=True,
            configured_provider=configured_provider,
            warning=fallback_warning,
            error=result.error,
        )

    return result


# ---------------------------------------------------------------------------
# Deterministic judgment
# ---------------------------------------------------------------------------


def _deterministic_judgment(citation_matches: list[CitationMatch]) -> FactCheckJudgmentOutput:
    """Derive a FactCheckJudgmentOutput from citation matches without LLM."""
    blocking: list[str] = []
    notes: list[str] = []

    for match in citation_matches:
        if (
            match.status == CitationStatus.unsupported
            and match.claim.importance == ClaimImportance.high
        ):
            blocking.append(f"Unsupported high-importance claim: {match.claim.text!r}")
        elif match.status == CitationStatus.unsupported:
            notes.append(f"Unsupported (non-blocking) claim: {match.claim.text!r}")
        elif match.status == CitationStatus.partially_supported:
            notes.append(f"Partially supported claim: {match.claim.text!r}")

    passed = len(blocking) == 0
    return FactCheckJudgmentOutput(
        passed=passed,
        revision_required=not passed,
        blocking_issues=blocking,
        revision_notes=notes,
        confidence="high",  # deterministic — confidence in the logic is high
    )


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _format_claim_summary(claims: list, citation_matches: list[CitationMatch]) -> str:
    if not citation_matches:
        return "No claims extracted."
    rows = []
    for m in citation_matches:
        rows.append(
            f"- [{m.claim.importance.value}] {m.claim.text!r} → {m.status.value}"
        )
    return "\n".join(rows)


def _format_source_summary(source_scores: list[SourceScore]) -> str:
    if not source_scores:
        return "No sources available."
    rows = []
    for s in source_scores[:5]:
        rows.append(f"- {s.domain} (score={s.overall_score:.2f}, mock={s.is_mock})")
    return "\n".join(rows)
