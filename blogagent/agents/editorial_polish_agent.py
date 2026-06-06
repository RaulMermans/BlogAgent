"""Editorial Polish Agent — improves publish-readiness of the article.

Permission class: write_draft

Runs at most once per pipeline. Triggered when publishability_evaluation.polish_required=True.
Calls the LLM (when BLOGAGENT_USE_LLM_EDITOR=true) to improve voice, specificity,
intro, conclusion, and sensory/contextual detail.

Does not invent unsupported facts. Does not remove citations. Does not invent
product notes not in the evidence table.
"""

from __future__ import annotations

import json
import os
from typing import Optional

from pydantic import BaseModel

from blogagent.llm import client as llm_client
from blogagent.llm.schemas import LLMResult

_MOCK_MODEL = "mock-1.0"
_MOCK_PROVIDER = "mock"


class EditorialPolishOutput(BaseModel):
    polished_markdown: str
    polish_summary: list[str]
    remaining_issues: list[str]
    publishability_confidence: float  # 0.0–1.0


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


def _mock_polish(
    article_markdown: str,
    publishability_evaluation: dict,
) -> EditorialPolishOutput:
    """Deterministic mock polish — returns article unchanged with explanatory summary."""
    defects = publishability_evaluation.get("defects", [])
    defect_types = [d.get("type", "unknown") for d in defects]
    return EditorialPolishOutput(
        polished_markdown=article_markdown,
        polish_summary=[
            f"Mock polish: {len(defects)} issue(s) noted "
            f"({', '.join(defect_types) if defect_types else 'none'}). "
            "No LLM provider configured — article returned without polish changes."
        ],
        remaining_issues=[d.get("message", "") for d in defects[:3]],
        publishability_confidence=0.5,
    )


_EDITORIAL_POLISH_PROMPT = """\
You are a senior personal-blog editor. Your task is to polish this article so it is
ready to publish with minimal human editing.

Publishability issues to address:
{defect_summary}

Active editorial skills:
{skill_briefs}

Topic: {topic}
Is recommendation: {is_recommendation}
Requested count: {requested_count}
Evidence limited: {evidence_limited}

Polish rules (MANDATORY):
1. Strengthen the intro — open with a specific observation, scene, or editorial thesis.
   No generic openers like "In today's world" or "Are you looking for".
2. Add editorial voice and opinion. Use "worth it", "skip", "the standout pick", etc.
3. For fragrance/beauty: weave in sensory language (scent notes, mood, occasion, longevity)
   ONLY when the evidence table already contains that information. Never invent notes.
4. Make recommendations specific: include "best for" context and practical advice.
5. Improve conclusion — end with an editorial recommendation or memorable insight.
6. Remove content-mill phrasing ("comprehensive guide", "look no further", "dive in").
7. If evidence-limited (fewer items than requested): frame the reduced count elegantly.
   Example: "We found five fragrances with enough source coverage to recommend with confidence."
8. Preserve all citations and inline links — do not remove or change URLs.
9. Preserve financial disclaimers if present.
10. Do not add new factual claims not present in the original article.
11. Do not invent product names, notes, or statistics.

Return the polished article as JSON with polished_markdown and revision_summary fields.

Original article:
{article}
"""


class _PolishOutput(BaseModel):
    polished_markdown: str
    revision_summary: str


def polish_article(
    article_markdown: str,
    topic: str,
    publishability_evaluation: dict,
    evidence_table_summary: str,
    selected_skills: list[str],
    is_recommendation: bool,
    requested_count: Optional[int],
    evidence_sufficiency: Optional[dict],
    polish_handoff: dict | None = None,
    tone_profile: dict | None = None,
) -> LLMResult:
    """Polish the article for publish-readiness.

    Returns an LLMResult wrapping EditorialPolishOutput.
    """
    if not _use_llm():
        return _mock_llm_result(_mock_polish(article_markdown, publishability_evaluation))

    from blogagent.skills.registry import get_skill_briefs  # noqa: PLC0415

    defects = publishability_evaluation.get("defects", [])
    defect_summary = (
        "\n".join(
            f"- [{d.get('type', 'unknown')}] ({d.get('severity', 'medium')}): "
            f"{d.get('message', '')}"
            for d in defects
        )
        or "No specific defects listed."
    )

    skill_briefs = get_skill_briefs(selected_skills) or "(none)"
    evidence_limited = (
        evidence_sufficiency is not None
        and evidence_sufficiency.get("recommended_action") == "evidence_limited"
    )

    system_prompt = _EDITORIAL_POLISH_PROMPT.format(
        defect_summary=defect_summary,
        skill_briefs=skill_briefs,
        topic=topic,
        is_recommendation=str(is_recommendation),
        requested_count=str(requested_count) if requested_count is not None else "not specified",
        evidence_limited=str(evidence_limited),
        article=article_markdown[:5000],
    )
    if polish_handoff:
        system_prompt += (
            "\n\nSTRUCTURED POLISH HANDOFF:\n"
            + json.dumps(polish_handoff, indent=2)
            + "\nThe locked candidate list and structure are immutable."
        )
    if tone_profile:
        system_prompt += (
            "\n\nTONE PROFILE (voice only; never change the candidate contract):\n"
            + json.dumps(tone_profile, indent=2)
        )

    result = llm_client.generate_structured(
        system_prompt=system_prompt,
        user_prompt=(
            "Polish the article. Return JSON with polished_markdown and revision_summary."
        ),
        output_model=_PolishOutput,
    )

    if result.is_mock or result.data is None:
        return _fallback_llm_result(
            _mock_polish(article_markdown, publishability_evaluation),
            result,
        )

    raw: _PolishOutput = result.data
    polish_output = EditorialPolishOutput(
        polished_markdown=raw.polished_markdown,
        polish_summary=[raw.revision_summary] if raw.revision_summary else [],
        remaining_issues=[],
        publishability_confidence=0.82,
    )

    return LLMResult(
        data=polish_output,
        provider=result.provider,
        model=result.model,
        is_mock=result.is_mock,
        configured_provider=result.configured_provider,
        warning=result.warning,
        error=result.error,
    )
