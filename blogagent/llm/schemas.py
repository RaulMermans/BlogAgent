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


class RevisionOutput(BaseModel):
    revised_markdown: str
    revision_summary: str


class LLMResult(BaseModel):
    """Wrapper returned by generate_structured()."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    data: Any | None = None  # parsed BaseModel instance, or None on failure
    provider: str
    model: str
    is_mock: bool
    warning: str | None = None
    error: str | None = None
    raw_text: str | None = None
