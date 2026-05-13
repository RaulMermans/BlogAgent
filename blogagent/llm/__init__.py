"""LLM client layer for BlogAgent.

Public surface:
    generate_structured — call an LLM and parse structured output
    LLMResult          — result wrapper
    All output schema classes
"""

from blogagent.llm.client import generate_structured
from blogagent.llm.schemas import (
    ClaimExtractionOutput,
    ClaimItem,
    DraftOutput,
    FactCheckJudgmentOutput,
    LLMResult,
    OutlineOutput,
    ResearchPlanOutput,
    RevisionOutput,
)

__all__ = [
    "generate_structured",
    "LLMResult",
    "ResearchPlanOutput",
    "OutlineOutput",
    "DraftOutput",
    "ClaimExtractionOutput",
    "ClaimItem",
    "FactCheckJudgmentOutput",
    "RevisionOutput",
]
