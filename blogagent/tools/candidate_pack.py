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

# Heading words that indicate a string is a section label, not a product name
_HEADING_WORDS: frozenset[str] = frozenset(
    {
        "buying",
        "choosing",
        "guide",
        "tips",
        "introduction",
        "conclusion",
        "overview",
        "summary",
        "how",
        "why",
        "what",
        "when",
        "where",
        "best",
        "top",
        "affordable",
        "luxury",
    }
)
# Navigation / metadata fragments that must not appear in display names
_NAV_FRAGMENTS: tuple[str, ...] = (
    "photos",
    "specs",
    "review",
    "click here",
    "read more",
    "see all",
    "source:",
    "via:",
    "from:",
    "article:",
    "section:",
)

CandidatePackMode = Literal[
    "evidence_locked",
    "editorial_shortlist",
    "exact",
    "evidence_limited",
    "below_minimum",
    "not_applicable",
]
CandidatePackStatus = Literal["exact", "evidence_limited", "below_minimum", "not_applicable"]

CandidatePackQualityMode = Literal["exact", "evidence_limited", "editorial_shortlist", "failed"]
CandidatePackPublishCeiling = Literal[
    "publish_ready",
    "publish_ready_with_editorial_review",
    "draft_only_not_publish_ready",
]
CandidatePackRepairAction = Literal["proceed", "repair_candidates", "enrich_search", "fail_fast"]


class CandidatePackQualityReport(BaseModel):
    """Deterministic gate on CandidatePack quality before drafting begins."""

    passes: bool
    locked_count: int
    requested_count: int | None
    invalid_items: list[str] = Field(default_factory=list)
    dirty_name_items: list[str] = Field(default_factory=list)
    light_coverage_items: list[str] = Field(default_factory=list)
    missing_evidence_items: list[str] = Field(default_factory=list)
    mode: CandidatePackQualityMode
    publish_ceiling: CandidatePackPublishCeiling
    repair_action: CandidatePackRepairAction


def build_candidate_pack_quality_report(
    pack: "CandidatePack",
    query_contract: QueryContract | dict,
) -> CandidatePackQualityReport:
    """Gate the CandidatePack before passing to the writer.

    Rules:
    - exact mode requires locked_count == requested_count
    - exact mode cannot include invalid or dirty candidates
    - editorial_shortlist allows light-coverage candidates but forces editorial_review ceiling
    - failed pack must produce fail_fast or draft_only
    """
    contract = (
        query_contract
        if isinstance(query_contract, QueryContract)
        else QueryContract.model_validate(query_contract)
    )

    invalid_items: list[str] = []
    dirty_name_items: list[str] = []
    light_coverage_items: list[str] = []
    missing_evidence_items: list[str] = []

    adapter = get_adapter(contract.domain)

    for item in pack.items:
        name = item.display_name or item.canonical_name or ""
        # Invalid entity check
        if not adapter.is_valid_entity(name, contract):
            invalid_items.append(name)
            continue
        # Dirty name check
        if _is_dirty_display_name(name):
            dirty_name_items.append(name)
            continue
        # Evidence checks
        if not item.evidence_spans:
            missing_evidence_items.append(name)
        elif item.candidate_basis in {"editorial_discretion", "weak_signal"}:
            light_coverage_items.append(name)

    editorial = contract.recommendation_strictness == "editorial"
    requested = pack.requested_count
    locked = pack.final_target_count

    if pack.status == "below_minimum" or pack.mode == "not_applicable":
        return CandidatePackQualityReport(
            passes=pack.status == "not_applicable",
            locked_count=locked,
            requested_count=requested,
            invalid_items=invalid_items,
            dirty_name_items=dirty_name_items,
            light_coverage_items=light_coverage_items,
            missing_evidence_items=missing_evidence_items,
            mode="failed" if pack.status == "below_minimum" else "exact",
            publish_ceiling="draft_only_not_publish_ready"
            if pack.status == "below_minimum"
            else "publish_ready",
            repair_action="fail_fast" if pack.status == "below_minimum" else "proceed",
        )

    has_hard_failures = bool(invalid_items or dirty_name_items)
    has_soft_issues = bool(light_coverage_items or missing_evidence_items)

    if has_hard_failures:
        mode: CandidatePackQualityMode = "failed"
        passes = False
        publish_ceiling: CandidatePackPublishCeiling = "draft_only_not_publish_ready"
        repair_action: CandidatePackRepairAction = "repair_candidates"
    elif pack.status == "evidence_limited":
        mode = "evidence_limited"
        passes = locked >= (contract.minimum_publishable_items or 3)
        publish_ceiling = "publish_ready_with_editorial_review"
        repair_action = "proceed" if passes else "enrich_search"
    elif editorial:
        mode = "editorial_shortlist"
        passes = True
        publish_ceiling = (
            "publish_ready_with_editorial_review" if has_soft_issues else "publish_ready"
        )
        repair_action = "proceed"
    elif has_soft_issues:
        mode = "exact" if requested is None or locked == requested else "evidence_limited"
        passes = True
        publish_ceiling = "publish_ready_with_editorial_review"
        repair_action = "proceed"
    else:
        mode = "exact"
        passes = requested is None or locked == requested
        publish_ceiling = "publish_ready" if passes else "publish_ready_with_editorial_review"
        repair_action = "proceed" if passes else "enrich_search"

    return CandidatePackQualityReport(
        passes=passes,
        locked_count=locked,
        requested_count=requested,
        invalid_items=invalid_items,
        dirty_name_items=dirty_name_items,
        light_coverage_items=light_coverage_items,
        missing_evidence_items=missing_evidence_items,
        mode=mode,
        publish_ceiling=publish_ceiling,
        repair_action=repair_action,
    )


def _is_dirty_display_name(name: str) -> bool:
    """Return True if the name contains debris that should not appear in a heading."""
    if not name or not name.strip():
        return True
    lower = name.lower().strip()
    # Price debris
    if re.search(r"\$\d+|\d+\s*usd|\d+\s*eur", lower):
        return True
    # Navigation fragments
    for frag in _NAV_FRAGMENTS:
        if frag in lower:
            return True
    # Starts with a heading word that implies it's a section, not a product
    first_word = lower.split()[0].strip(".,;:!?\"'") if lower.split() else ""
    if first_word in {"how", "why", "what", "guide", "tips", "introduction", "conclusion"}:
        return True
    # Contains URL-like debris
    if "http" in lower or "www." in lower:
        return True
    # Too long for a product name (likely a prose fragment)
    if len(name) > 80:
        return True
    return False


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

    expanded, compound_rejections = _split_compound_candidates(ledger.allowed_candidates, contract)
    deduped = _deduplicate_allowed_candidates(expanded)
    deduped.sort(
        key=lambda candidate: (
            {"high": 0, "medium": 1, "low": 2}.get(candidate.candidate_confidence, 3),
            -_candidate_richness(candidate)[0],
        )
    )
    allowed_count = len(deduped)
    requested = contract.requested_count
    stronger = [
        candidate for candidate in deduped if candidate.candidate_confidence in {"high", "medium"}
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
            (index for index, existing in enumerate(deduped) if _are_aliases(existing, candidate)),
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
    canonical = (candidate.canonical_name or candidate.name or candidate.raw_mention).strip()
    raw_display = (
        candidate.raw_mention.strip()
        if candidate.candidate_basis == "known_entity"
        else _display_name_from_evidence(canonical, candidate.evidence_spans)
    )
    display = _sanitize_display_name(raw_display, canonical)
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


# Trailing words that describe a product variant rather than identify it —
# safe to drop from a heading once the core model name is established.
_TRAILING_DESCRIPTOR_WORDS: frozenset[str] = frozenset(
    {"everyday", "dress", "watch", "watches", "edition", "model", "version", "series"}
)


def _strip_trailing_descriptors(name: str) -> str:
    """Drop trailing variant/descriptor words and duplicate words from a heading.

    e.g. "Hamilton Khaki Field Field Watch" -> "Hamilton Khaki Field"
         "Tissot PRX Quartz Everyday" -> "Tissot PRX Quartz"
    Keeps at least two words so brand+model identity is preserved.
    """
    words = name.split()
    while len(words) > 2:
        last_lower = words[-1].lower().strip(".,;:")
        if last_lower in _TRAILING_DESCRIPTOR_WORDS:
            words.pop()
            continue
        if any(w.lower().strip(".,;:") == last_lower for w in words[:-1]):
            words.pop()
            continue
        break
    return " ".join(words)


def _sanitize_display_name(display: str, canonical_fallback: str) -> str:
    """Strip debris from a display name so it can safely appear as an article heading.

    Falls back to canonical_fallback if the display name is unusable.
    """
    name = display.strip()
    # Strip price debris, including a leading "~" approximation marker
    name = re.sub(r"~?\s*\$\d+[\d,.]*\s*", "", name).strip()
    # Strip trailing connectors like " which starts around", " right Photos"
    name = re.sub(
        r"\s+(?:which|that|right|photos?|specs?)\b.*$", "", name, flags=re.IGNORECASE
    ).strip()
    # Strip navigation fragments
    for frag in _NAV_FRAGMENTS:
        idx = name.lower().find(frag)
        if idx > 0:
            name = name[:idx].strip()
    # Strip leading/trailing punctuation
    name = name.strip(" -–—,;:.")
    # Drop trailing variant descriptors and duplicate words
    name = _strip_trailing_descriptors(name)
    if not name or len(name) < 3:
        name = canonical_fallback.strip()
    # Final length guard
    if len(name) > 80:
        # Try to truncate to the canonical name if it fits
        if canonical_fallback and len(canonical_fallback) <= 80:
            name = canonical_fallback.strip()
        else:
            name = name[:80].rsplit(" ", 1)[0].strip()
    return _smart_title(name) if name else canonical_fallback


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
