"""Output schemas for LLM-backed BlogAgent functions.

All schemas are Pydantic BaseModels so they can be used with
model_validate / model_json_schema for structured LLM output.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ResearchPlanOutput(BaseModel):
    research_questions: list[str]


class OutlineOutput(BaseModel):
    title: str
    sections: list[str]
    target_word_count: int = 1000
    seo_keywords: list[str] = Field(default_factory=list)


class DraftOutput(BaseModel):
    article_markdown: str
    meta_description: str
    seo_keywords: list[str] = Field(default_factory=list)


class ClaimItem(BaseModel):
    text: str
    importance: Literal["high", "medium", "low"]
    section: str = ""


class ClaimExtractionOutput(BaseModel):
    claims: list[ClaimItem]


class FactCheckJudgmentOutput(BaseModel):
    passed: bool
    revision_required: bool
    blocking_issues: list[str] = Field(default_factory=list)
    revision_notes: list[str] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"] = "medium"


class CitationJudgmentOutput(BaseModel):
    claim: str
    support_status: Literal["supported", "partially_supported", "unsupported"]
    confidence: Literal["low", "medium", "high"]
    explanation: str


class RevisionOutput(BaseModel):
    revised_markdown: str
    revision_summary: str


class LLMResult(BaseModel):
    """Wrapper returned by generate_structured() and agent functions.

    Fields:
        configured_provider: What BLOGAGENT_LLM_PROVIDER requested (or "mock" when LLM
            was not attempted for the stage). May differ from provider when fallback occurred.
        provider: The provider that actually produced the output ("mock", "anthropic", etc.).
        is_mock: True when output came from the mock data registry (fallback or intentional).
        warning: Set when a configured live provider fell back to mock.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    data: Any | None = None  # parsed BaseModel instance, or None on failure
    provider: str
    model: str
    is_mock: bool
    configured_provider: str | None = None  # what env requested; may differ from provider
    warning: str | None = None
    error: str | None = None
    raw_text: str | None = None
