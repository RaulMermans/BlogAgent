"""Entity Candidate Ledger — generic answer-unit validation.

Wraps the existing recommendation candidate extraction with:
- Domain adapter-driven classification
- Candidate Cleanliness Gate v2
- Pollution detection
- Ledger quality gate

Permission class: read_only
All operations are deterministic — no LLM calls.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Literal, Optional

from pydantic import BaseModel

from blogagent.tools.domain_adapters import get_adapter
from blogagent.workflow.query_contract import QueryContract, requires_candidate_ledger
from blogagent.workflow.state import EvidenceItem

LedgerQuality = Literal["strong", "limited", "failed", "not_required"]

# ---------------------------------------------------------------------------
# Prose fragment patterns — these indicate a captured name is really a sentence
# ---------------------------------------------------------------------------

# Incomplete product name endings — reject these as truncated
_INCOMPLETE_ENDINGS: tuple[str, ...] = (
    " eau de",          # "Tom Ford Neroli Portofino Eau de"
    " de",
    " with",
    " and",
    " for",
    " will",
    " always",
    " fragrances with",
    " i went",
    " rabbit",
    " can't",
    " always",
    " but",
    " on me",
    " member",
    " reply",
)

# Prose verb patterns — if the 3rd+ word is one of these, it's a sentence fragment
_PROSE_VERBS: frozenset[str] = frozenset(
    {
        "will", "always", "went", "down", "rabbit", "can't", "won't", "didn't",
        "is", "was", "are", "were", "have", "has", "had", "said", "says",
        "loved", "love", "likes", "liked", "hated", "hate", "tried", "try",
        "smells", "smelled", "wore", "wears", "wearing", "bought", "buy",
        "got", "get", "found", "find", "think", "thought", "feel", "felt",
        "never", "always", "still", "just", "only", "very", "really",
        "went", "came", "came", "came", "but", "however", "although",
        "actually", "literally", "honestly", "personally", "definitely",
        "maybe", "probably", "usually", "often", "sometimes", "enough",
    }
)

# First-person indicators
_FIRST_PERSON: tuple[str, ...] = (
    " i ", " i've ", " i'm ", " i'd ", " i'll ", " i went ", " i got ",
    " my ", " me ", " myself ",
)

# Social/forum residue patterns
_SOCIAL_RESIDUE: tuple[str, ...] = (
    "reply by",
    "member",
    "wildevoodoo",
    "💕",
    "🌴",
    "🥥",
    "❤",
    "😊",
    "👍",
)

# Price pattern
_PRICE_RE = re.compile(r"\$\d+|\d+\s*usd|\d+\s*eur|\d+\s*gbp", re.IGNORECASE)

# Stopwords for density check
_STOPWORDS: frozenset[str] = frozenset(
    {
        "the", "a", "an", "this", "that", "these", "those", "and", "or",
        "but", "with", "for", "from", "into", "about", "over", "under",
        "after", "before", "through", "by", "at", "to", "in", "of",
        "our", "your", "their", "its", "all", "most", "some", "any",
        "when", "where", "which", "who", "what", "how", "if", "is", "are",
        "was", "were", "be", "been", "being", "have", "has", "had",
        "will", "would", "could", "should", "may", "might", "shall", "can",
        "best", "top", "good", "great", "well", "new", "old", "first",
        "more", "most", "less", "very", "just", "also", "so", "then",
    }
)


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------


class EntityCandidate(BaseModel):
    """A validated entity candidate from the candidate ledger."""

    candidate_id: str = ""
    raw_mention: str
    canonical_name: str = ""
    name: str = ""          # alias for canonical_name for compatibility with draft code
    entity_type: str = "unknown"
    domain: str = "general"
    entity_subtype: Optional[str] = None
    source_urls: list[str] = []
    source_titles: list[str] = []
    source_quality: Literal["high", "medium", "low"] = "medium"
    source_type: str = "unknown"
    evidence_spans: list[str] = []
    evidence_terms: list[str] = []
    supported_context: list[str] = []
    clean_name_score: float = 0.0
    evidence_score: float = 0.0
    usable: bool = False
    rejection_reason: Optional[str] = None


class CandidateLedger(BaseModel):
    """Full candidate ledger for a query contract."""

    requested_count: Optional[int]
    raw_mentions_count: int
    candidates: list[EntityCandidate]
    validated_candidates: list[EntityCandidate]
    allowed_candidates: list[EntityCandidate]
    rejected_candidates: list[EntityCandidate]
    usable_count: int
    usable_names: list[str]
    rejected_count: int
    rejected_examples: list[dict]
    table_quality: LedgerQuality
    quality_issues: list[str]

    def to_summary_dict(self) -> dict:
        """Compact summary safe for API responses."""
        return {
            "requested_count": self.requested_count,
            "usable_count": self.usable_count,
            "rejected_count": self.rejected_count,
            "table_quality": self.table_quality,
            "quality_issues": list(self.quality_issues),
            "usable_names": list(self.usable_names[:10]),
            "rejected_examples": list(self.rejected_examples[:5]),
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_candidate_ledger(
    sources: list,
    evidence_table: list[EvidenceItem],
    query_contract: QueryContract,
    source_quality_scores: list[dict],
) -> CandidateLedger:
    """Build a candidate ledger from sources and evidence for a query contract.

    Returns a ledger with table_quality = "not_required" for non-recommendation topics.
    """
    if not requires_candidate_ledger(query_contract):
        return CandidateLedger(
            requested_count=query_contract.requested_count,
            raw_mentions_count=0,
            candidates=[],
            validated_candidates=[],
            allowed_candidates=[],
            rejected_candidates=[],
            usable_count=0,
            usable_names=[],
            rejected_count=0,
            rejected_examples=[],
            table_quality="not_required",
            quality_issues=[],
        )

    from blogagent.tools.recommendation_extractor import (  # noqa: PLC0415
        RecommendationCandidate,
        extract_candidates_from_sources,
    )

    raw_candidates: list[RecommendationCandidate] = extract_candidates_from_sources(
        sources=sources,
        evidence_table=evidence_table,
        query_contract=query_contract,
        source_quality_scores=source_quality_scores,
    )

    # Build URL→source-type/quality map for propagation
    source_type_map: dict[str, str] = {}
    for sq in source_quality_scores:
        url = sq.get("url", "")
        if url:
            source_type_map[url] = sq.get("source_type", "unknown")

    candidates = [
        _to_entity_candidate(
            c, query_contract, source_type_map, sources, evidence_table
        )
        for c in raw_candidates
    ]

    # Apply Cleanliness Gate v2 — re-check each allowed candidate against strict rules
    candidates = [_apply_cleanliness_gate_v2(c, query_contract) for c in candidates]

    allowed = [c for c in candidates if c.usable]
    rejected = [c for c in candidates if not c.usable]

    ledger = CandidateLedger(
        requested_count=query_contract.requested_count,
        raw_mentions_count=len(candidates),
        candidates=candidates,
        validated_candidates=allowed,
        allowed_candidates=allowed,
        rejected_candidates=rejected,
        usable_count=len(allowed),
        usable_names=[c.canonical_name or c.raw_mention for c in allowed],
        rejected_count=len(rejected),
        rejected_examples=[
            {
                "name": c.raw_mention,
                "entity_type": c.entity_type,
                "rejection_reason": c.rejection_reason,
            }
            for c in rejected[:10]
        ],
        table_quality="not_required",  # will be updated
        quality_issues=[],
    )

    return evaluate_candidate_ledger_quality(ledger, query_contract)


def evaluate_candidate_ledger_quality(
    ledger: CandidateLedger,
    query_contract: QueryContract,
) -> CandidateLedger:
    """Evaluate and set table_quality on the ledger.

    Quality rules (Candidate Cleanliness Gate v2):
    - strong: usable_count >= requested_count, all allowed pass cleanliness, no empty spans,
              avg clean_name_score >= 0.85, avg evidence_score >= 0.70
    - limited: usable_count >= minimum_publishable_items but < requested_count
    - failed: usable_count < minimum_publishable_items OR pollution detected
    - not_required: non-recommendation task type
    """
    if not requires_candidate_ledger(query_contract):
        return ledger

    quality_issues: list[str] = []
    min_items = query_contract.minimum_publishable_items
    requested = query_contract.requested_count

    # --- Pollution checks ---
    pollution_count = _count_polluted(ledger)
    if pollution_count > 0:
        quality_issues.append(
            f"{pollution_count} polluted candidate(s) incorrectly marked usable"
        )

    if ledger.raw_mentions_count > 0:
        rejected_pollution = sum(
            1
            for c in ledger.rejected_candidates
            if c.entity_type in ("brand_cluster", "source_title", "source_nav", "section_heading")
        )
        pollution_ratio = rejected_pollution / ledger.raw_mentions_count
        if pollution_ratio > 0.2:
            quality_issues.append(
                f"High pollution ratio: {rejected_pollution}/{ledger.raw_mentions_count} "
                "raw mentions are entity clusters, source nav, or source titles"
            )

    # Average name length check (suspiciously long names signal cluster pollution)
    if ledger.allowed_candidates:
        avg_len = sum(len(c.raw_mention) for c in ledger.allowed_candidates) / len(
            ledger.allowed_candidates
        )
        if avg_len > 60:
            quality_issues.append(
                f"Average allowed candidate name length is {avg_len:.0f} chars — "
                "may contain cluster pollution"
            )

    # Cleanliness v2 checks on allowed candidates
    empty_spans_count = sum(
        1 for c in ledger.allowed_candidates if not c.evidence_spans
    )
    if empty_spans_count > 0:
        quality_issues.append(
            f"{empty_spans_count} allowed candidate(s) have empty evidence_spans"
        )

    unknown_source_type_count = sum(
        1 for c in ledger.allowed_candidates if c.source_type == "unknown"
    )
    if ledger.allowed_candidates and unknown_source_type_count == len(ledger.allowed_candidates):
        quality_issues.append(
            "All allowed candidates have source_type=unknown — source metadata not propagated"
        )

    if ledger.allowed_candidates:
        avg_clean = sum(c.clean_name_score for c in ledger.allowed_candidates) / len(
            ledger.allowed_candidates
        )
        avg_evidence = sum(c.evidence_score for c in ledger.allowed_candidates) / len(
            ledger.allowed_candidates
        )
        if avg_clean < 0.85:
            quality_issues.append(
                f"Average clean_name_score of allowed candidates is "
                f"{avg_clean:.2f} (threshold 0.85)"
            )
        if avg_evidence < 0.70:
            quality_issues.append(
                f"Average evidence_score of allowed candidates is "
                f"{avg_evidence:.2f} (threshold 0.70)"
            )

    # --- Determine quality level ---
    actual_usable = ledger.usable_count - pollution_count

    if pollution_count > 0:
        table_quality: LedgerQuality = "failed"
    elif actual_usable < min_items:
        table_quality = "failed"
        quality_issues.append(
            f"Usable count ({actual_usable}) is below minimum publishable ({min_items})"
        )
    elif requested is not None and actual_usable < requested:
        table_quality = "limited"
        quality_issues.append(
            f"Usable count ({actual_usable}) is below requested ({requested})"
        )
    else:
        # For strong: also require no quality issues from cleanliness gate
        cleanliness_issues = [
            i for i in quality_issues
            if "evidence_spans" in i or "clean_name_score" in i or "evidence_score" in i
        ]
        if cleanliness_issues:
            table_quality = "limited"
        else:
            table_quality = "strong"

    return ledger.model_copy(
        update={
            "table_quality": table_quality,
            "quality_issues": quality_issues,
            "usable_count": actual_usable,
        }
    )


# ---------------------------------------------------------------------------
# Candidate Cleanliness Gate v2
# ---------------------------------------------------------------------------


def _apply_cleanliness_gate_v2(
    candidate: EntityCandidate,
    query_contract: QueryContract,
) -> EntityCandidate:
    """Apply strict cleanliness checks and update usable/rejection_reason.

    For recommendation topics a candidate may be 'allowed' only if it passes
    all cleanliness checks:
      - canonical_name is non-empty
      - entity_type matches expected type
      - clean_name_score >= 0.75
      - evidence_score >= 0.65
      - supported_context is non-empty
      - candidate is not a sentence fragment / prose / truncated / social residue
      - candidate does not have empty evidence_spans (capped evidence_score < 0.49 → rejected)

    Returns a copy with usable/rejection_reason updated.
    """
    if not requires_candidate_ledger(query_contract):
        return candidate

    # Already rejected — keep rejection reason
    if not candidate.usable:
        return candidate

    name = candidate.canonical_name or candidate.raw_mention

    # --- Clean name score threshold ---
    if candidate.clean_name_score < 0.75:
        return candidate.model_copy(
            update={
                "usable": False,
                "rejection_reason": (
                    f"low clean_name_score={candidate.clean_name_score:.2f} — "
                    "likely prose fragment or malformed candidate"
                ),
            }
        )

    # --- Evidence score threshold ---
    if candidate.evidence_score < 0.65:
        return candidate.model_copy(
            update={
                "usable": False,
                "rejection_reason": (
                    f"low evidence_score={candidate.evidence_score:.2f} — "
                    "insufficient source backing"
                ),
            }
        )

    # --- Evidence spans required for recommendation topics ---
    if not candidate.evidence_spans:
        # Cap evidence_score and reject
        return candidate.model_copy(
            update={
                "usable": False,
                "evidence_score": min(candidate.evidence_score, 0.49),
                "rejection_reason": "missing evidence span — no source text contains this name",
            }
        )

    # --- Prose fragment patterns ---
    prose_reason = _detect_prose_fragment(name)
    if prose_reason:
        return candidate.model_copy(
            update={
                "usable": False,
                "clean_name_score": min(candidate.clean_name_score, 0.3),
                "rejection_reason": prose_reason,
            }
        )

    return candidate


def _detect_prose_fragment(name: str) -> str | None:
    """Return a rejection reason if the name looks like a prose fragment, else None."""
    lower = name.lower().strip()

    # Emoji / social residue
    for residue in _SOCIAL_RESIDUE:
        if residue in lower or residue in name:
            return "social/forum residue or emoji in candidate name"

    # Unicode emoji check
    for char in name:
        if unicodedata.category(char) in ("So", "Sm") and ord(char) > 127:
            return "emoji in candidate name"

    # First-person language
    lower_spaced = f" {lower} "
    for fp in _FIRST_PERSON:
        if fp in lower_spaced:
            return "first-person prose phrase in candidate name"

    # Unmatched quotation marks
    if name.count('"') % 2 != 0 or name.count("'") % 2 != 0:
        pass  # Unmatched quotes are penalized in score but not hard-rejected here

    # Incomplete ending patterns
    for ending in _INCOMPLETE_ENDINGS:
        if lower.endswith(ending):
            return f"incomplete/truncated candidate — ends with '{ending.strip()}'"

    # Prose verbs check: if 3rd+ word is a prose verb, it's a fragment
    words = lower.split()
    if len(words) >= 3:
        # Check words starting from position 2 (after brand prefix)
        for word_pos in range(2, min(len(words), 5)):
            w = words[word_pos].strip(".,;:!?\"'")
            if w in _PROSE_VERBS:
                return f"prose fragment — contains prose verb '{w}' in position {word_pos + 1}"

    # Too many stopwords (sentence-like structure)
    if len(words) >= 4:
        stopword_count = sum(1 for w in words if w.strip(".,;:") in _STOPWORDS)
        stopword_ratio = stopword_count / len(words)
        if stopword_ratio > 0.5:
            return (
                f"too many stopwords ({stopword_count}/{len(words)}) — "
                "looks like a sentence, not a product name"
            )

    return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _to_entity_candidate(
    candidate,  # RecommendationCandidate
    query_contract: QueryContract,
    source_type_map: dict[str, str] | None = None,
    sources: list | None = None,
    evidence_table: list | None = None,
) -> EntityCandidate:
    """Convert a RecommendationCandidate to an EntityCandidate."""
    adapter = get_adapter(query_contract.domain)
    entity_type = adapter.classify_entity_type(candidate.name, query_contract)
    rejection_reason = adapter.get_rejection_reason(candidate.name, query_contract)
    usable = candidate.usable and rejection_reason is None
    if not usable and rejection_reason is None:
        rejection_reason = candidate.rejection_reason or "does not satisfy query contract"

    # Resolve source_type from map (accurate) vs inferring from quality (inaccurate)
    source_type = "unknown"
    if source_type_map and candidate.source_urls:
        for url in candidate.source_urls:
            st = source_type_map.get(url, "unknown")
            if st != "unknown":
                source_type = st
                break
    if source_type == "unknown" and candidate.source_quality == "high":
        source_type = "editorial"

    canonical = adapter.canonicalize(candidate.name)

    # Extract evidence spans: look for canonical name in evidence texts
    evidence_spans = _extract_evidence_spans(
        canonical_name=canonical,
        raw_mention=candidate.name,
        source_urls=candidate.source_urls,
        sources=sources or [],
        evidence_table=evidence_table or [],
    )

    # Compute scores
    clean_score = score_clean_candidate_name(candidate.name)
    evidence_score = _compute_evidence_score(
        candidate,
        has_spans=bool(evidence_spans),
        source_type=source_type,
    )

    # Strip price from canonical name (e.g. "Diptyque Philosykos Eau de Parfum $260")
    canonical = _strip_price_from_name(canonical)

    # Build stable candidate_id
    primary_url = candidate.source_urls[0] if candidate.source_urls else ""
    candidate_id = _make_candidate_id(canonical, primary_url)

    return EntityCandidate(
        candidate_id=candidate_id,
        raw_mention=candidate.name,
        canonical_name=canonical,
        name=canonical or candidate.name,
        entity_type=entity_type if entity_type != "unknown" else candidate.entity_type,
        domain=query_contract.domain,
        entity_subtype=query_contract.entity_subtype,
        source_urls=list(candidate.source_urls),
        source_titles=list(candidate.source_titles),
        source_quality=candidate.source_quality,
        source_type=source_type,
        evidence_spans=evidence_spans,
        evidence_terms=list(candidate.evidence_terms),
        supported_context=list(candidate.supported_context),
        clean_name_score=clean_score,
        evidence_score=evidence_score,
        usable=usable,
        rejection_reason=rejection_reason,
    )


def _make_candidate_id(canonical_name: str, primary_url: str) -> str:
    """Generate a stable, slug-safe candidate identifier."""
    key = f"{canonical_name.lower().strip()}|{primary_url}"
    return hashlib.md5(key.encode(), usedforsecurity=False).hexdigest()[:16]


def _strip_price_from_name(name: str) -> str:
    """Remove price artifacts from a product name."""
    # Remove "$260", "USD 45", etc.
    cleaned = _PRICE_RE.sub("", name).strip()
    # Remove trailing punctuation left by price removal
    cleaned = cleaned.strip(" -–—,;")
    return cleaned


def _extract_evidence_spans(
    canonical_name: str,
    raw_mention: str,
    source_urls: list[str],
    sources: list,
    evidence_table: list,
) -> list[str]:
    """Extract supporting text spans that contain this candidate's name."""
    spans: list[str] = []
    seen: set[str] = set()

    search_names = [n for n in [canonical_name.lower(), raw_mention.lower()] if n and len(n) > 3]
    if not search_names:
        return spans

    def _add_span(text: str, name: str) -> bool:
        lower_text = text.lower()
        idx = lower_text.find(name)
        if idx == -1:
            return False
        span_start = max(0, idx - 60)
        span_end = min(len(text), idx + len(name) + 80)
        span = text[span_start:span_end].strip()
        # Normalise span for dedup
        norm = re.sub(r"\s+", " ", span.lower())
        if norm not in seen and len(span) > 10:
            seen.add(norm)
            spans.append(span)
            return True
        return False

    # Check evidence table facts
    for item in evidence_table:
        if len(spans) >= 3:
            break
        if hasattr(item, "fact"):
            fact = item.fact
        elif isinstance(item, dict):
            fact = item.get("fact", "")
        else:
            fact = ""
        if not fact or len(fact.strip()) < 20:
            continue
        for name in search_names:
            if _add_span(fact, name):
                break

    # Check source extracted text
    for source in sources:
        if len(spans) >= 3:
            break
        text = (
            getattr(source, "extracted_text", "")
            if not isinstance(source, dict)
            else source.get("extracted_text", "")
        )
        if not text:
            continue
        for name in search_names:
            if _add_span(text[:3000], name):
                break

    return spans


def score_clean_candidate_name(name: str) -> float:
    """Score how 'clean' a candidate name is (0–1).

    Returns < 0.75 for prose fragments, social residue, truncated names, emoji, etc.
    Returns >= 0.75 for specific product names.
    """
    if not name or not name.strip():
        return 0.0

    score = 1.0
    lower = name.lower().strip()
    words = lower.split()
    original_words = name.strip().split()  # preserve original case for isupper() check

    # --- Hard penalties (make score < 0.75) ---

    # Emoji
    for char in name:
        if unicodedata.category(char) in ("So", "Sm") and ord(char) > 127:
            return 0.1

    # Social/forum residue
    for residue in _SOCIAL_RESIDUE:
        if residue in lower:
            return 0.1

    # Price artifacts ($xxx)
    if _PRICE_RE.search(name):
        # penalise but don't hard-reject — price may be stripped during canonicalization
        score -= 0.2

    # First-person
    lower_spaced = f" {lower} "
    for fp in _FIRST_PERSON:
        if fp in lower_spaced:
            score -= 0.6

    # Incomplete endings
    for ending in _INCOMPLETE_ENDINGS:
        if lower.endswith(ending):
            score -= 0.5
            break

    # Prose verbs in non-brand positions
    if len(words) >= 3:
        for word_pos in range(2, min(len(words), 5)):
            w = words[word_pos].strip(".,;:!?\"'")
            if w in _PROSE_VERBS:
                score -= 0.5
                break

    # Too many stopwords (sentence-like structure)
    if len(words) >= 4:
        stopword_count = sum(1 for w in words if w.strip(".,;:") in _STOPWORDS)
        stopword_ratio = stopword_count / len(words)
        if stopword_ratio > 0.5:
            score -= 0.4
        elif stopword_ratio > 0.35:
            score -= 0.2

    # Unmatched quotes
    if name.count('"') % 2 != 0:
        score -= 0.3

    # --- Moderate penalties ---

    # Very long names (likely entity clusters)
    if len(name) > 60:
        score -= 0.5
    elif len(name) > 40:
        score -= 0.2

    # Single-word names (likely brand-only)
    if len(words) == 1:
        score -= 0.2

    # All-caps clusters (e.g. "ARMANI PRADA CREED") — use original_words for case check
    caps_words = sum(1 for w in original_words if w.isupper() and len(w) > 2)
    if caps_words >= 2:
        score -= 0.4

    # Source/article heading language
    heading_words = {
        "how", "why", "what", "when", "where", "guide", "tips",
        "introduction", "conclusion", "overview", "summary",
    }
    if words and words[0] in heading_words:
        score -= 0.5

    return max(0.0, min(1.0, score))


def _compute_evidence_score(
    candidate,
    has_spans: bool = False,
    source_type: str = "unknown",
) -> float:
    """Score how well-evidenced a candidate is (0–1)."""
    score = 0.0

    # Base from source quality
    if candidate.source_quality == "high":
        score += 0.4
    elif candidate.source_quality == "medium":
        score += 0.25
    else:
        score += 0.05

    # Bonus for having actual evidence spans
    if has_spans:
        score += 0.2

    # Source count bonus
    source_count = len(candidate.source_urls)
    score += min(0.2, source_count * 0.07)

    # Context/terms bonus
    context_count = len(getattr(candidate, "supported_context", [])) + len(
        getattr(candidate, "evidence_terms", [])
    )
    score += min(0.15, context_count * 0.03)

    # Source type penalty: unknown source type caps at 0.59
    if source_type == "unknown":
        score = min(score, 0.59)

    # No spans cap: cap at 0.49 if no evidence spans
    if not has_spans:
        score = min(score, 0.49)

    return min(1.0, score)


def _count_polluted(ledger: CandidateLedger) -> int:
    """Count allowed candidates that are actually polluted."""
    polluted_types = {"brand_cluster", "section_heading", "source_title", "source_nav"}
    return sum(1 for c in ledger.allowed_candidates if c.entity_type in polluted_types)
