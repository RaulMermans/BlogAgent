"""Build the locked recommendation candidate pack used by article agents.

Permission class: read_only
All operations are deterministic and source-bound.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

from blogagent.tools.entity_candidate_ledger import CandidateLedger
from blogagent.workflow.query_contract import QueryContract

CandidatePackMode = Literal["exact", "evidence_limited", "below_minimum", "not_applicable"]


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


class CandidatePack(BaseModel):
    requested_count: int | None
    allowed_count: int
    final_target_count: int
    mode: CandidatePackMode
    minimum_publishable_items: int
    evidence_limited: bool
    items: list[CandidatePackItem] = Field(default_factory=list)
    rejected_items: list[dict] = Field(default_factory=list)
    count_policy: str
    locked_candidate_ids: list[str] = Field(default_factory=list)
    locked_display_names: list[str] = Field(default_factory=list)


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
            minimum_publishable_items=minimum,
            evidence_limited=False,
            rejected_items=[c.model_dump() for c in ledger.rejected_candidates],
            count_policy="Candidate locking is not applicable to this task.",
        )

    deduped = _deduplicate_allowed_candidates(ledger.allowed_candidates)
    allowed_count = len(deduped)
    requested = contract.requested_count

    if allowed_count < minimum:
        mode: CandidatePackMode = "below_minimum"
        final_target_count = allowed_count
        count_policy = (
            f"Only {allowed_count} source-backed candidates passed validation; "
            f"the minimum publishable count is {minimum}. Produce a draft-only evidence report."
        )
    elif requested is not None and allowed_count < requested:
        mode = "evidence_limited"
        final_target_count = allowed_count
        count_policy = (
            f"Use all {allowed_count} locked candidates and explain that the evidence "
            f"did not support the requested {requested} items."
        )
    else:
        mode = "exact"
        final_target_count = requested if requested is not None else allowed_count
        count_policy = (
            f"Use exactly {final_target_count} locked candidates, once in Quick Picks "
            "and once as individual detail sections."
        )

    selected = deduped[:final_target_count]
    items = [_to_pack_item(candidate) for candidate in selected]
    return CandidatePack(
        requested_count=requested,
        allowed_count=allowed_count,
        final_target_count=final_target_count,
        mode=mode,
        minimum_publishable_items=minimum,
        evidence_limited=mode == "evidence_limited",
        items=items,
        rejected_items=[c.model_dump() for c in ledger.rejected_candidates],
        count_policy=count_policy,
        locked_candidate_ids=[item.candidate_id for item in items],
        locked_display_names=[item.display_name for item in items],
    )


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
    display = _display_name_from_evidence(canonical, candidate.evidence_spans)
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
