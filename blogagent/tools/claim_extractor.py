"""claim_extractor tool.

Permission class: read_only

Extracts factual claims from a blog draft.

If BLOGAGENT_USE_LLM_FACTCHECK=false (default):
  Heuristic extraction: parses markdown headings and body text.
  - Sentences containing numbers, percentages, or comparative phrases → high importance.
  - Regular sentences → medium importance.
  - Falls back to one generic claim if extraction yields nothing.

If BLOGAGENT_USE_LLM_FACTCHECK=true:
  Calls the LLM client for semantically rich claim extraction.
  Falls back to heuristic extraction if the LLM call fails.
"""

from __future__ import annotations

import os
import re
import warnings

from pydantic import BaseModel

from blogagent.workflow.state import Claim, ClaimImportance

# Patterns that mark a claim as high importance.
_HIGH_IMPORTANCE_RE = re.compile(
    r"(\d[\d,.]*\s*%)"  # percentages: 85%, 3.5%
    r"|(\d+\s*(?:million|billion|trillion|thousand))"  # large numbers
    r"|\b(more than|less than|over|under|at least|up to|increased by|decreased by"
    r"|higher than|lower than|fastest|slowest|largest|smallest|first|doubled|tripled)\b",
    re.IGNORECASE,
)

_SECTION_HEADING_RE = re.compile(r"^#{2,3}\s+(.+)$", re.MULTILINE)
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|^", re.MULTILINE)


class ClaimExtractInput(BaseModel):
    draft: str
    topic: str


class ClaimExtractOutput(BaseModel):
    claims: list[Claim]
    error: str | None = None


def claim_extractor(input: ClaimExtractInput) -> ClaimExtractOutput:
    """Extract factual claims from the draft."""
    if os.getenv("BLOGAGENT_USE_LLM_FACTCHECK", "false").strip().lower() == "true":
        return _llm_extract(input)
    return _heuristic_extract(input)


# ---------------------------------------------------------------------------
# Heuristic extraction (default)
# ---------------------------------------------------------------------------


def _heuristic_extract(input: ClaimExtractInput) -> ClaimExtractOutput:
    claims: list[Claim] = []

    # 1. Extract section headings as medium-importance claims.
    for match in _SECTION_HEADING_RE.finditer(input.draft):
        heading = match.group(1).strip()
        if heading.lower() not in ("introduction", "conclusion", "summary"):
            claims.append(
                Claim(
                    text=f"{heading} is a key aspect of {input.topic}.",
                    importance=ClaimImportance.medium,
                    section=heading,
                )
            )
        if len(claims) >= 2:
            break

    # 2. Scan sentences in the body for numerical/comparative patterns → high.
    # Split on sentence boundaries; skip heading lines.
    body_lines = [
        line
        for line in input.draft.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    body_text = " ".join(body_lines)
    raw_sentences = [
        s.strip() for s in re.split(r"(?<=[.!?])\s+", body_text) if len(s.strip()) > 20
    ]

    high_added = 0
    for sentence in raw_sentences:
        if high_added >= 1:
            break
        if _HIGH_IMPORTANCE_RE.search(sentence):
            # Determine section from proximity — use nearest prior heading or "Body"
            section = _find_section_for_sentence(input.draft, sentence)
            claims.append(
                Claim(
                    text=sentence,
                    importance=ClaimImportance.high,
                    section=section,
                )
            )
            high_added += 1

    # 3. Fallback: guarantee at least one claim.
    if not claims:
        claims.append(
            Claim(
                text=f"{input.topic} is an important subject with multiple dimensions.",
                importance=ClaimImportance.medium,
                section="Introduction",
            )
        )

    return ClaimExtractOutput(claims=claims[:3])


def _find_section_for_sentence(draft: str, sentence: str) -> str:
    """Return the section heading that appears most recently before the sentence."""
    pos = draft.find(sentence[:30])
    if pos == -1:
        return "Body"
    preceding = draft[:pos]
    headings = _SECTION_HEADING_RE.findall(preceding)
    return headings[-1] if headings else "Body"


# ---------------------------------------------------------------------------
# LLM-backed extraction (optional)
# ---------------------------------------------------------------------------


def _llm_extract(input: ClaimExtractInput) -> ClaimExtractOutput:
    from blogagent.agents import prompts  # noqa: PLC0415
    from blogagent.llm import client as llm_client  # noqa: PLC0415
    from blogagent.llm.schemas import ClaimExtractionOutput  # noqa: PLC0415

    result = llm_client.generate_structured(
        system_prompt=prompts.FACT_CHECK_PROMPT.format(
            draft=input.draft[:4000], topic=input.topic, evidence_table=""
        ),
        user_prompt="Extract all factual claims as a JSON object.",
        output_model=ClaimExtractionOutput,
    )

    if result.error or result.data is None:
        warnings.warn(
            f"LLM claim extraction failed: {result.error or 'no data'}; using heuristic fallback.",
            stacklevel=2,
        )
        return _heuristic_extract(input)

    extraction: ClaimExtractionOutput = result.data
    importance_map = {
        "high": ClaimImportance.high,
        "medium": ClaimImportance.medium,
        "low": ClaimImportance.low,
    }
    claims = [
        Claim(
            text=c.text,
            importance=importance_map.get(c.importance, ClaimImportance.medium),
            section=c.section,
        )
        for c in extraction.claims
    ]
    return ClaimExtractOutput(claims=claims)
