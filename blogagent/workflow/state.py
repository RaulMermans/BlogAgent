from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field

ExecutionMode = Literal["mock", "hybrid", "live"]


class CitationStatus(str, Enum):
    supported = "supported"
    partially_supported = "partially_supported"
    unsupported = "unsupported"


class ClaimImportance(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class SearchResult(BaseModel):
    url: str
    title: str
    snippet: str
    domain: str
    is_mock: bool = False


class SourcePacket(BaseModel):
    url: str
    title: str
    domain: str
    extracted_text: str
    word_count: int = 0
    author: str = ""
    date: str = ""
    publisher: str = ""
    is_mock: bool = False
    extraction_status: Literal["success", "failed", "mock"] = "success"
    error_message: Optional[str] = None


class SourceScore(BaseModel):
    url: str
    title: str
    domain: str
    credibility_score: float = Field(ge=0.0, le=1.0)
    relevance_score: float = Field(ge=0.0, le=1.0)
    recency_score: float = Field(ge=0.0, le=1.0)
    overall_score: float = Field(ge=0.0, le=1.0)
    notes: str = ""
    is_mock: bool = False


class EvidenceItem(BaseModel):
    fact: str
    source_url: str
    source_title: str
    publisher_domain: str
    confidence: float = Field(ge=0.0, le=1.0)
    used_for: str


class BlogOutline(BaseModel):
    title: str
    sections: list[str]
    target_word_count: int = 1000
    seo_keywords: list[str] = Field(default_factory=list)


class Claim(BaseModel):
    text: str
    importance: ClaimImportance
    section: str = ""


class CitationMatch(BaseModel):
    claim: Claim
    status: CitationStatus
    supporting_sources: list[str] = Field(default_factory=list)
    notes: str = ""


class FactCheckReport(BaseModel):
    total_claims: int
    supported_count: int
    partially_supported_count: int
    unsupported_count: int
    matches: list[CitationMatch] = Field(default_factory=list)
    passed: bool = False
    blocking_issues: list[str] = Field(default_factory=list)


class ArticlePackage(BaseModel):
    article_markdown: str
    source_list: list[SourceScore]
    fact_check_report: FactCheckReport
    claim_support_statuses: list[CitationMatch]
    revision_summary: str
    title: str = ""
    slug: str = ""
    meta_description: str = ""
    seo_keywords: list[str] = Field(default_factory=list)
    run_id: str = ""
    created_at: str = ""
    topic: str = ""


class BlogRunState(BaseModel):
    topic: str
    research_questions: list[str] = Field(default_factory=list)
    search_results: list[SearchResult] = Field(default_factory=list)
    selected_sources: list[SourcePacket] = Field(default_factory=list)
    source_scores: list[SourceScore] = Field(default_factory=list)
    evidence_table: list[EvidenceItem] = Field(default_factory=list)
    outline: Optional[BlogOutline] = None
    draft: str = ""
    # SEO fields set by write_article_draft — used in the final package
    draft_meta_description: str = ""
    draft_seo_keywords: list[str] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    citation_matches: list[CitationMatch] = Field(default_factory=list)
    fact_check_report: Optional[FactCheckReport] = None
    final_article_package: Optional[ArticlePackage] = None
    revision_count: int = 0
    revision_summary: str = ""
    run_id: str = ""
    blocked: bool = False
    block_reason: str = ""
    requires_approval: bool = False
    # Recommendation / financial intent flags (set deterministically by guardrail)
    is_recommendation: bool = False
    is_financial: bool = False
    # Skill selection (deterministic, set after intent detection)
    selected_skills: list[str] = Field(default_factory=list)
    # Requested item count extracted from topic (e.g. "top 10" → 10)
    requested_count: Optional[int] = None
    # Source quality classification (high/medium/low per source)
    source_quality_scores: list[dict] = Field(default_factory=list)
    # Quality evaluation result (dict-serialized QualityEvaluationOutput)
    quality_evaluation: Optional[dict] = None
    # Final validation warnings (appended after post-revision quality check)
    final_validation_warnings: list[str] = Field(default_factory=list)
    # Final validation structured defects (dicts with type/severity/message/fixable)
    final_validation_defects: list[dict] = Field(default_factory=list)
    # Final validation status: "passed" | "passed_with_warnings" | "failed"
    final_validation_status: str = ""
    # True when final validator accepted a reduced recommendation count due to evidence limits
    evidence_limited_count_accepted: bool = False
    # Human-readable agent run trace (built at end of pipeline)
    run_trace: list[str] = Field(default_factory=list)
    # Run trace fields
    warnings: list[str] = Field(default_factory=list)
    provider_events: list[str] = Field(default_factory=list)
    stage_timings: dict[str, float] = Field(default_factory=dict)
    execution_mode: ExecutionMode = "mock"
    # Evidence sufficiency evaluation (dict-serialized EvidenceSufficiencyResult)
    evidence_sufficiency: Optional[dict] = None
    # Number of web search passes run (initial + enrichment)
    search_pass_count: int = 1
    # Queries used for enrichment search pass
    enrichment_queries: list[str] = Field(default_factory=list)
    # Publishability evaluation (dict-serialized PublishabilityEvaluation)
    publishability_evaluation: Optional[dict] = None
    # Summary of editorial polish changes (list of strings)
    polish_summary: list[str] = Field(default_factory=list)
    # Publishability score 0-100 (extracted from publishability_evaluation for convenience)
    publishability_score: int = 0
    # Final publish readiness: "publish_ready" | "publish_ready_with_warnings" | "draft_only_not_publish_ready"
    publish_ready_status: str = ""
