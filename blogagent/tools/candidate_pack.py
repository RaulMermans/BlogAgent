"""Build the locked recommendation candidate pack used by article agents.

Permission class: read_only
All operations are deterministic and source-bound.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from blogagent.tools.domain_adapters import get_adapter
from blogagent.tools.entity_candidate_ledger import CandidateLedger
from blogagent.tools.recommendation_policy import (
    CandidateBasis,
    CandidateConfidence,
    has_compound_connector,
    split_compound_candidate_name,
)
from blogagent.workflow.query_contract import QueryContract

CandidatePackMode = Literal[
    "evidence_locked",
    "editorial_shortlist",
    "exact",
    "evidence_limited",
    "below_minimum",
    "not_applicable",
]
CandidatePackStatus = Literal["exact", "evidence_limited", "below_minimum", "not_applicable"]


class CandidatePackItem(BaseModel):
    candidate_id: str
    canonical_name: str
    display_name: str
    section_heading: str
    source_url: str | None = None
    source_title: str | None = None
    source_quality: str | None = None
    source_type: str | None = None
    evidence_spans: list[str] = Field(default_factory=list)
    evidence_terms: list[str] = Field(default_factory=list)
    supported_context: list[str] = Field(default_factory=list)
    entity_type: str
    entity_subtype: str | None = None
    candidate_confidence: CandidateConfidence = "medium"
    candidate_basis: CandidateBasis = "weak_signal"
    needs_review: bool = False
    editorial_note: str | None = None


class CandidatePack(BaseModel):
    requested_count: int | None
    allowed_count: int
    final_target_count: int
    mode: CandidatePackMode
    status: CandidatePackStatus = "exact"
    recommendation_strictness: str = "standard"
    evidence_mode: str = "source_aware"
    minimum_publishable_items: int
    evidence_limited: bool
    items: list[CandidatePackItem] = Field(default_factory=list)
    rejected_items: list[dict] = Field(default_factory=list)
    count_policy: str
    locked_candidate_ids: list[str] = Field(default_factory=list)
    locked_display_names: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_mode(cls, value):
        """Accept pre-policy serialized packs while emitting the new mode shape."""
        if not isinstance(value, dict):
            return value
        data = dict(value)
        legacy_mode = data.get("mode")
        if legacy_mode in {"exact", "evidence_limited", "below_minimum"}:
            data.setdefault("status", legacy_mode)
            data["mode"] = "evidence_locked"
        return data


def build_candidate_pack(
    query_contract: QueryContract | dict,
    entity_candidate_ledger: CandidateLedger | dict,
) -> CandidatePack:
    """Create the exact, deduplicated candidate set the article must preserve."""
    contract = (
        query_contract
        if isinstance(query_contract, QueryContract)
        else QueryContract.model_validate(query_contract)
    )
    ledger = (
        entity_candidate_ledger
        if isinstance(entity_candidate_ledger, CandidateLedger)
        else CandidateLedger.model_validate(entity_candidate_ledger)
    )
    minimum = contract.minimum_publishable_items

    if contract.task_type != "recommendation":
        return CandidatePack(
            requested_count=contract.requested_count,
            allowed_count=0,
            final_target_count=0,
            mode="not_applicable",
            status="not_applicable",
            recommendation_strictness=contract.recommendation_strictness,
            evidence_mode=contract.evidence_mode,
            minimum_publishable_items=minimum,
            evidence_limited=False,
            rejected_items=[c.model_dump() for c in ledger.rejected_candidates],
            count_policy="Candidate locking is not applicable to this task.",
        )

    expanded, compound_rejections = _split_compound_candidates(
        ledger.allowed_candidates, contract
    )
    deduped = _deduplicate_allowed_candidates(expanded)
    deduped.sort(
        key=lambda candidate: (
            {"high": 0, "medium": 1, "low": 2}.get(
                candidate.candidate_confidence, 3
            ),
            -_candidate_richness(candidate)[0],
        )
    )
    allowed_count = len(deduped)
    requested = contract.requested_count
    stronger = [
        candidate
        for candidate in deduped
        if candidate.candidate_confidence in {"high", "medium"}
    ]

    if allowed_count < minimum:
        status: CandidatePackStatus = "below_minimum"
        final_target_count = allowed_count
        count_policy = (
            f"Only {allowed_count} clean candidates passed validation; "
            f"the minimum publishable count is {minimum}. Produce a draft-only report."
        )
    elif requested is not None and allowed_count < requested:
        status = "evidence_limited"
        final_target_count = allowed_count
        if contract.recommendation_strictness == "editorial":
            count_policy = (
                f"Use all {allowed_count} clean candidates as a tighter shortlist and "
                f"retitle the article to {allowed_count} items."
            )
        else:
            count_policy = (
                f"Use all {allowed_count} locked candidates and explain that the evidence "
                f"did not support the requested {requested} items."
            )
    else:
        status = "exact"
        if requested is not None:
            final_target_count = requested
        elif contract.recommendation_strictness == "editorial" and len(stronger) >= minimum:
            final_target_count = len(stronger)
        else:
            final_target_count = allowed_count
        count_policy = (
            f"Use exactly {final_target_count} locked candidates, once in Quick Picks "
            "and once as individual detail sections."
        )

    selection_pool = (
        stronger
        if (
            requested is None
            and contract.recommendation_strictness == "editorial"
            and len(stronger) >= minimum
        )
        else deduped
    )
    selected = selection_pool[:final_target_count]
    items = [_to_pack_item(candidate) for candidate in selected]
    mode: CandidatePackMode = (
        "editorial_shortlist"
        if contract.recommendation_strictness == "editorial"
        else "evidence_locked"
    )
    return CandidatePack(
        requested_count=requested,
        allowed_count=allowed_count,
        final_target_count=final_target_count,
        mode=mode,
        status=status,
        recommendation_strictness=contract.recommendation_strictness,
        evidence_mode=contract.evidence_mode,
        minimum_publishable_items=minimum,
        evidence_limited=status == "evidence_limited",
        items=items,
        rejected_items=[
            *[c.model_dump() for c in ledger.rejected_candidates],
            *compound_rejections,
        ],
        count_policy=count_policy,
        locked_candidate_ids=[item.candidate_id for item in items],
        locked_display_names=[item.display_name for item in items],
    )


def _split_compound_candidates(
    candidates: list, contract: QueryContract
) -> tuple[list, list[dict]]:
    adapter = get_adapter(contract.domain)
    expanded: list = []
    rejected: list[dict] = []
    for candidate in candidates:
        name = candidate.canonical_name or candidate.name or candidate.raw_mention
        parts = split_compound_candidate_name(name)
        if len(parts) == 1:
            if has_compound_connector(name) or not adapter.is_valid_entity(name, contract):
                rejected.append(
                    {
                        "name": name,
                        "rejection_reason": (
                            "compound candidate could not be split confidently"
                            if has_compound_connector(name)
                            else adapter.get_rejection_reason(name, contract)
                            or "invalid candidate identity"
                        ),
                    }
                )
            else:
                expanded.append(candidate)
            continue
        if not all(adapter.is_valid_entity(part, contract) for part in parts):
            rejected.append(
                {
                    "name": name,
                    "rejection_reason": "compound candidate could not be split confidently",
                }
            )
            continue
        for index, part in enumerate(parts):
            expanded.append(
                candidate.model_copy(
                    update={
                        "candidate_id": f"{candidate.candidate_id}-split-{index + 1}",
                        "raw_mention": part,
                        "canonical_name": adapter.canonicalize(part),
                        "name": adapter.canonicalize(part),
                    }
                )
            )
    return expanded, rejected


def _deduplicate_allowed_candidates(candidates: list) -> list:
    deduped: list = []
    for candidate in candidates:
        duplicate_index = next(
            (
                index
                for index, existing in enumerate(deduped)
                if _are_aliases(existing, candidate)
            ),
            None,
        )
        if duplicate_index is None:
            deduped.append(candidate)
            continue
        existing = deduped[duplicate_index]
        if _candidate_richness(candidate) > _candidate_richness(existing):
            deduped[duplicate_index] = candidate
    return deduped


def _are_aliases(left, right) -> bool:
    left_name = _normalise_name(left.canonical_name or left.name or left.raw_mention)
    right_name = _normalise_name(right.canonical_name or right.name or right.raw_mention)
    if not left_name or not right_name:
        return False
    if left_name == right_name:
        return True

    left_tokens = set(left_name.split())
    right_tokens = set(right_name.split())
    shorter, longer = (
        (left_tokens, right_tokens)
        if len(left_tokens) <= len(right_tokens)
        else (right_tokens, left_tokens)
    )
    meaningful_shorter = shorter - {"eau", "de", "toilette", "parfum", "perfume", "the"}
    if len(meaningful_shorter) >= 2 and meaningful_shorter.issubset(longer):
        spans = " ".join(left.evidence_spans + right.evidence_spans).lower()
        return all(token in spans for token in meaningful_shorter)
    return False


def _candidate_richness(candidate) -> tuple[int, int, int]:
    name = candidate.canonical_name or candidate.name or candidate.raw_mention
    return (len(candidate.evidence_spans), len(candidate.source_urls), len(name))


def _to_pack_item(candidate) -> CandidatePackItem:
    canonical = (
        candidate.canonical_name or candidate.name or candidate.raw_mention
    ).strip()
    display = (
        candidate.raw_mention.strip()
        if candidate.candidate_basis == "known_entity"
        else _display_name_from_evidence(canonical, candidate.evidence_spans)
    )
    source_url = candidate.source_urls[0] if candidate.source_urls else None
    source_title = candidate.source_titles[0] if candidate.source_titles else None
    return CandidatePackItem(
        candidate_id=candidate.candidate_id or _normalise_name(canonical).replace(" ", "-"),
        canonical_name=canonical,
        display_name=display,
        section_heading=display,
        source_url=source_url,
        source_title=source_title,
        source_quality=candidate.source_quality,
        source_type=candidate.source_type,
        evidence_spans=list(candidate.evidence_spans),
        evidence_terms=list(candidate.evidence_terms),
        supported_context=list(candidate.supported_context),
        entity_type=candidate.entity_type,
        entity_subtype=candidate.entity_subtype,
        candidate_confidence=candidate.candidate_confidence,
        candidate_basis=candidate.candidate_basis,
        needs_review=candidate.candidate_confidence == "low",
        editorial_note=(
            "Fits the topic as a clean editorial pick; verify objective details before publishing."
            if candidate.candidate_basis in {"editorial_discretion", "weak_signal"}
            else None
        ),
    )


def _display_name_from_evidence(canonical_name: str, evidence_spans: list[str]) -> str:
    """Use evidence-backed casing and suffixes without inventing name components."""
    canonical_norm = _normalise_name(canonical_name)
    best = canonical_name.strip()
    for span in evidence_spans:
        clean_span = re.sub(r"\s+", " ", span).strip()
        if not clean_span:
            continue
        span_norm = _normalise_name(clean_span)
        if canonical_norm and canonical_norm in span_norm:
            for suffix in ("eau de toilette", "eau de parfum", "eau de cologne", "parfum"):
                if suffix in span_norm and suffix not in canonical_norm:
                    base = canonical_name.rstrip()
                    if base.lower().endswith(" eau") and suffix.startswith("eau "):
                        base = base[:-4]
                    best = f"{base} {suffix.title()}"
                    break
            match = re.search(re.escape(canonical_name), clean_span, re.IGNORECASE)
            if match:
                evidence_casing = clean_span[match.start() : match.end()]
                if evidence_casing:
                    best = evidence_casing + best[len(canonical_name) :]
            break
    return _smart_title(best)


def _smart_title(value: str) -> str:
    lower_words = {"de", "of", "the", "and", "for"}
    words = []
    for index, word in enumerate(value.split()):
        if word == "&":
            words.append(word)
        elif index > 0 and word.lower() in lower_words:
            words.append(word.lower())
        elif word.isupper() and len(word) <= 4:
            words.append(word)
        else:
            words.append(word[:1].upper() + word[1:])
    return " ".join(words)


def _normalise_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
