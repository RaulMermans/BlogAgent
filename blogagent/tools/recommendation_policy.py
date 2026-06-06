"""Risk-tiered evidence policy for recommendation articles.

Permission class: read_only
All operations are deterministic.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel

RecommendationStrictness = Literal["strict", "standard", "editorial"]
EvidenceMode = Literal["source_required", "source_aware", "editorial_discretion"]
PublishPolicy = Literal[
    "hard_block_on_ungrounded",
    "warn_on_weak_grounding",
    "allow_with_editorial_review",
]
ExactCountPolicy = Literal["require_requested_count", "prefer_requested_count"]
CandidateConfidence = Literal["high", "medium", "low"]
CandidateBasis = Literal[
    "source_exact",
    "source_title",
    "known_entity",
    "editorial_discretion",
    "weak_signal",
]


class EvidencePolicy(BaseModel):
    """Deterministic recommendation policy selected from domain risk."""

    strictness_level: RecommendationStrictness
    evidence_mode: EvidenceMode
    publish_policy: PublishPolicy
    grounding_required: bool
    exact_count_policy: ExactCountPolicy
    allow_editorial_discretion: bool
    publishable_with_warnings_allowed: bool


class RecommendationPolicyInput(BaseModel):
    """Typed input for deterministic recommendation policy resolution."""

    domain: str


_STRICT_DOMAINS = {
    "finance",
    "medical",
    "health",
    "legal",
    "safety",
    "regulated_products",
    "investment",
    "security",
}
_STANDARD_DOMAINS = {
    "software_tools",
    "b2b_tools",
    "education_technology",
    "productivity_products",
    "technical_products",
}
_EDITORIAL_DOMAINS = {
    "beauty_fragrance",
    "beauty_makeup",
    "fashion_lifestyle",
    "consumer_products",
    "travel",
    "food",
    "home",
    "culture",
}


def evidence_policy_for_domain(domain: str) -> EvidencePolicy:
    """Return the recommendation evidence policy for a normalized domain."""
    normalized = (domain or "general").strip().lower()
    if normalized in _STRICT_DOMAINS:
        return EvidencePolicy(
            strictness_level="strict",
            evidence_mode="source_required",
            publish_policy="hard_block_on_ungrounded",
            grounding_required=True,
            exact_count_policy="require_requested_count",
            allow_editorial_discretion=False,
            publishable_with_warnings_allowed=False,
        )
    if normalized in _EDITORIAL_DOMAINS:
        return EvidencePolicy(
            strictness_level="editorial",
            evidence_mode="source_aware",
            publish_policy="allow_with_editorial_review",
            grounding_required=False,
            exact_count_policy="prefer_requested_count",
            allow_editorial_discretion=True,
            publishable_with_warnings_allowed=True,
        )
    return EvidencePolicy(
        strictness_level="standard",
        evidence_mode="source_aware",
        publish_policy="warn_on_weak_grounding",
        grounding_required=False,
        exact_count_policy="prefer_requested_count",
        allow_editorial_discretion=False,
        publishable_with_warnings_allowed=True,
    )


def resolve_recommendation_policy(
    input: RecommendationPolicyInput,
) -> EvidencePolicy:
    """Resolve a structured recommendation policy.

    Permission class: read_only.
    """
    return evidence_policy_for_domain(input.domain)


def split_compound_candidate_name(name: str) -> list[str]:
    """Split explicit ``A or B``/``A and B`` compounds into clean names.

    Ampersands are intentionally not split because they commonly occur inside
    brand names such as ``Dolce & Gabbana``.
    """
    clean = re.sub(r"\s+", " ", name or "").strip()
    if not clean:
        return []
    parts = [part.strip(" ,;:/") for part in re.split(r"\s+(?:or|and)\s+", clean)]
    if len(parts) <= 1 or any(len(part.split()) == 0 for part in parts):
        return [clean]
    return parts


def has_compound_connector(name: str) -> bool:
    """Return True when a candidate contains an explicit compound connector."""
    return bool(re.search(r"\s+(?:or|and)\s+", name or "", re.IGNORECASE))
