"""Typed artifacts passed between BlogAgent article stages."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from blogagent.tools.candidate_pack import CandidatePack


class WriterHandoff(BaseModel):
    query_contract: dict
    candidate_pack: dict
    tone_profile: dict | None = None
    required_structure: list[str] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=list)
    evidence_policy: str
    output_contract: dict


class WriterOutputAudit(BaseModel):
    used_candidate_ids: list[str] = Field(default_factory=list)
    missing_candidate_ids: list[str] = Field(default_factory=list)
    unknown_candidate_names: list[str] = Field(default_factory=list)
    declared_count: int | None = None
    quick_picks_count: int = 0
    detail_sections_count: int = 0
    evidence_limited_explanation_present: bool = False
    passes_locked_structure: bool = False


class ReviewDefect(BaseModel):
    defect_id: str
    type: str
    severity: Literal["low", "medium", "high"]
    candidate_id: str | None = None
    expected: str | int | None = None
    actual: str | int | None = None
    required_fix: str
    fix_scope: Literal["structure", "candidate", "evidence", "style", "metadata", "safety"]


class ReviewPacket(BaseModel):
    passes: bool
    contract_passes: bool
    editorial_passes: bool
    defects: list[ReviewDefect] = Field(default_factory=list)
    missing_candidate_ids: list[str] = Field(default_factory=list)
    unsupported_entities: list[str] = Field(default_factory=list)
    required_revision_mode: Literal["none", "targeted_repair", "full_rewrite", "draft_only"]
    reviewer_summary: str


class RevisionPlan(BaseModel):
    revision_strategy: Literal["targeted_repair", "full_rewrite", "draft_only"]
    defects_to_fix: list[str] = Field(default_factory=list)
    locked_candidate_ids_to_preserve: list[str] = Field(default_factory=list)
    sections_to_add: list[str] = Field(default_factory=list)
    sections_to_rewrite: list[str] = Field(default_factory=list)
    forbidden_changes: list[str] = Field(default_factory=list)


class RevisionOutputAudit(BaseModel):
    resolved_defect_ids: list[str] = Field(default_factory=list)
    unresolved_defect_ids: list[str] = Field(default_factory=list)
    used_candidate_ids: list[str] = Field(default_factory=list)
    missing_candidate_ids: list[str] = Field(default_factory=list)
    unknown_candidate_names: list[str] = Field(default_factory=list)
    structure_preserved: bool = False
    passes_locked_structure: bool = False


class PolishHandoff(BaseModel):
    article_markdown: str
    candidate_pack: dict
    tone_profile: dict | None = None
    locked_candidate_ids: list[str] = Field(default_factory=list)
    allowed_changes: list[str] = Field(default_factory=list)
    forbidden_changes: list[str] = Field(default_factory=list)


class PolishOutputAudit(BaseModel):
    structure_preserved: bool
    used_candidate_ids: list[str] = Field(default_factory=list)
    missing_candidate_ids: list[str] = Field(default_factory=list)
    unknown_candidate_names: list[str] = Field(default_factory=list)
    count_changed: bool
    candidate_list_changed: bool


def build_writer_handoff(
    query_contract: dict,
    candidate_pack: CandidatePack | dict,
    tone_profile: dict | None = None,
) -> WriterHandoff:
    pack = (
        candidate_pack
        if isinstance(candidate_pack, CandidatePack)
        else CandidatePack.model_validate(candidate_pack)
    )
    if pack.mode == "below_minimum":
        required_structure = [
            "What was searched",
            "Validated candidates found",
            "Why not publish-ready",
            "What evidence is missing",
            "Suggested next search/refinement",
        ]
    else:
        required_structure = [
            f"H1 declaring {pack.final_target_count} recommendations",
            "Quick Picks with every locked candidate",
            "How We Chose",
            "One detail section per locked candidate",
            "Buying or Choosing Tips",
            "Final Takeaway",
        ]
    forbidden = [
        "add recommendations outside CandidatePack",
        "remove locked candidates",
        "rename locked candidates",
        "change the count mode",
        "invent evidence, citations, statistics, or quotes",
    ]
    if pack.mode == "evidence_limited":
        forbidden.append("claim the originally requested count in the title or body")
    return WriterHandoff(
        query_contract=query_contract,
        candidate_pack=pack.model_dump(),
        tone_profile=tone_profile,
        required_structure=required_structure,
        forbidden_actions=forbidden,
        evidence_policy=(
            "Use only evidence attached to CandidatePack items. Preserve source URLs and "
            "state uncertainty when evidence is thin."
        ),
        output_contract={
            "candidate_list_locked": True,
            "required_candidate_ids": pack.locked_candidate_ids,
            "final_target_count": pack.final_target_count,
            "mode": pack.mode,
            "recommended_entities_required": pack.mode != "below_minimum",
        },
    )


def build_polish_handoff(
    article_markdown: str,
    candidate_pack: CandidatePack | dict,
    tone_profile: dict | None = None,
) -> PolishHandoff:
    pack = (
        candidate_pack
        if isinstance(candidate_pack, CandidatePack)
        else CandidatePack.model_validate(candidate_pack)
    )
    return PolishHandoff(
        article_markdown=article_markdown,
        candidate_pack=pack.model_dump(),
        tone_profile=tone_profile,
        locked_candidate_ids=list(pack.locked_candidate_ids),
        allowed_changes=[
            "improve flow, sentence quality, transitions, and tone",
            "reduce repetition",
            "improve SEO phrasing without changing factual meaning",
        ],
        forbidden_changes=[
            "remove, add, merge, or rename candidates",
            "change count or evidence-limited mode",
            "remove Quick Picks, detail sections, citations, or source URLs",
            "turn the recommendation article into a generic guide",
        ],
    )
