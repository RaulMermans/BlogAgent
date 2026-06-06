"""Revision Agent — quality-driven draft revision.

Revises a draft based on structured defects from QualityEvaluationOutput.
Falls back to deterministic mock output when BLOGAGENT_USE_LLM_EDITOR=false.

Returns the existing RevisionOutput schema so the pipeline can store
revised_markdown and revision_summary in state without schema changes.
"""

from __future__ import annotations

import json
import os
from typing import Optional

from blogagent.agents import prompts
from blogagent.llm import client as llm_client
from blogagent.llm.schemas import LLMResult, RevisionOutput
from blogagent.skills.registry import get_skill_briefs

_MOCK_MODEL = "mock-1.0"
_MOCK_PROVIDER = "mock"


def _use_llm() -> bool:
    return os.getenv("BLOGAGENT_USE_LLM_EDITOR", "false").strip().lower() == "true"


def _mock_llm_result(data: object, configured_provider: str = "mock") -> LLMResult:
    return LLMResult(
        data=data,
        provider=_MOCK_PROVIDER,
        model=_MOCK_MODEL,
        is_mock=True,
        configured_provider=configured_provider,
    )


def _fallback_llm_result(data: object, base: LLMResult) -> LLMResult:
    fallback_warning = base.warning or (f"LLM call failed: {base.error}" if base.error else None)
    return LLMResult(
        data=data,
        provider=_MOCK_PROVIDER,
        model=_MOCK_MODEL,
        is_mock=True,
        configured_provider=base.configured_provider,
        warning=fallback_warning,
        error=base.error,
    )


def _mock_quality_revision(
    draft: str,
    quality_evaluation: dict,
    is_financial: bool,
    candidate_pack: dict | None = None,
    query_contract: dict | None = None,
) -> RevisionOutput:
    """Deterministic mock revision that applies simple fixes."""
    defects = quality_evaluation.get("defects", [])
    defect_types = [d.get("type", "unknown") for d in defects]
    summary = (
        f"Mock quality revision: {len(defects)} defect(s) noted "
        f"({', '.join(defect_types) if defect_types else 'none'}). "
        "No LLM provider configured — structural fixes applied where possible."
    )
    revised = draft

    if candidate_pack and query_contract:
        from blogagent.tools.locked_entity_repair import (  # noqa: PLC0415
            repair_locked_recommendation_article,
        )

        repair = repair_locked_recommendation_article(
            revised,
            candidate_pack,
            query_contract,
        )
        revised = repair.repaired_markdown
        if repair.repair_applied:
            summary += " " + " ".join(repair.repair_summary)

    # Apply financial disclaimer if missing (deterministic fix).
    if is_financial and not _has_disclaimer(draft):
        disclaimer = (
            "\n> **Disclaimer**: This article is for educational purposes only and does not "
            "constitute financial advice. Consult a qualified financial adviser before making "
            "investment decisions.\n"
        )
        lines = draft.split("\n")
        for i, line in enumerate(lines):
            if line.startswith("# "):
                lines.insert(i + 1, disclaimer)
                break
        revised = "\n".join(lines)

    return RevisionOutput(revised_markdown=revised, revision_summary=summary)


def _has_disclaimer(draft: str) -> bool:
    lower = draft.lower()
    return (
        "not financial advice" in lower
        or "educational purposes only" in lower
        or "consult a qualified financial" in lower
    )


def revise_with_quality_context(
    topic: str,
    draft: str,
    quality_evaluation: dict,
    warnings: list[str],
    is_recommendation: bool,
    is_financial: bool,
    requested_count: Optional[int],
    selected_skills: list[str],
    source_quality_scores: list[dict],
    review_packet: dict | None = None,
    revision_plan: dict | None = None,
    candidate_pack: dict | None = None,
    query_contract: dict | None = None,
    tone_profile: dict | None = None,
) -> LLMResult:
    """Revise the draft using quality evaluation defects as guidance.

    In mock mode (BLOGAGENT_USE_LLM_EDITOR=false), applies simple deterministic
    fixes (e.g. adds financial disclaimer if missing) and returns the draft
    otherwise unchanged with an explanatory summary.
    """
    if not _use_llm():
        return _mock_llm_result(
            _mock_quality_revision(
                draft,
                quality_evaluation,
                is_financial,
                candidate_pack=candidate_pack,
                query_contract=query_contract,
            )
        )

    defects = quality_evaluation.get("defects", [])
    defect_lines = (
        "\n".join(
            f"- [{d.get('type', 'unknown')}] ({d.get('severity', 'medium')}): "
            f"{d.get('message', '')}"
            for d in defects
        )
        or "No specific defects listed."
    )

    skill_briefs = get_skill_briefs(selected_skills) or "(none)"

    high = sum(1 for s in source_quality_scores if s.get("quality") == "high")
    medium = sum(1 for s in source_quality_scores if s.get("quality") == "medium")
    low = sum(1 for s in source_quality_scores if s.get("quality") == "low")
    source_quality_summary = f"{high} high, {medium} medium, {low} low quality sources"

    system_prompt = prompts.QUALITY_REVISION_PROMPT.format(
        defects=defect_lines,
        skill_briefs=skill_briefs,
        source_quality_summary=source_quality_summary,
        is_recommendation=str(is_recommendation),
        requested_count=(str(requested_count) if requested_count is not None else "not specified"),
        draft=draft[:4000],
    )
    if review_packet:
        system_prompt += "\n\nREVIEW PACKET:\n" + json.dumps(review_packet, indent=2)
    if revision_plan:
        system_prompt += "\n\nREVISION PLAN:\n" + json.dumps(revision_plan, indent=2)
    if candidate_pack:
        system_prompt += (
            "\n\nLOCKED CANDIDATE PACK:\n"
            + json.dumps(candidate_pack, indent=2)
            + "\nThe candidate list is locked. Resolve defects inside this structure."
        )
    if tone_profile:
        system_prompt += "\n\nTONE PROFILE (voice only; do not change contract):\n" + json.dumps(
            tone_profile, indent=2
        )

    result = llm_client.generate_structured(
        system_prompt=system_prompt,
        user_prompt=(
            "Revise the article. Return a JSON object with revised_markdown and revision_summary."
        ),
        output_model=RevisionOutput,
    )
    if result.is_mock:
        return _fallback_llm_result(
            _mock_quality_revision(
                draft,
                quality_evaluation,
                is_financial,
                candidate_pack=candidate_pack,
                query_contract=query_contract,
            ),
            result,
        )
    return result
