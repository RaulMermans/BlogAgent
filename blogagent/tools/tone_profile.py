"""Bounded tone profiles that affect prose but never article contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ToneProfileId = Literal[
    "editorial_magazine",
    "practical_buying_guide",
    "expert_analyst",
    "personal_blog",
    "luxury_premium",
    "seo_neutral",
]


class ToneProfile(BaseModel):
    id: ToneProfileId
    label: str
    description: str
    writing_rules: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    forbidden_style_patterns: list[str] = Field(default_factory=list)


_PROFILES: dict[str, ToneProfile] = {
    "editorial_magazine": ToneProfile(
        id="editorial_magazine",
        label="Editorial Magazine",
        description="Polished editorial voice with confident, evidence-bound judgments.",
        writing_rules=["use varied rhythm", "lead with a specific editorial observation"],
        preferred_skills=["personal-blog-voice", "publishability-review"],
        forbidden_style_patterns=["content-mill openers", "generic superlatives"],
    ),
    "practical_buying_guide": ToneProfile(
        id="practical_buying_guide",
        label="Practical Buying Guide",
        description="Direct, useful guidance centered on fit, tradeoffs, and use cases.",
        writing_rules=["prioritize practical distinctions", "make caveats easy to scan"],
        preferred_skills=["product-recommendation-depth"],
        forbidden_style_patterns=["ornamental filler", "unsupported certainty"],
    ),
    "expert_analyst": ToneProfile(
        id="expert_analyst",
        label="Expert Analyst",
        description="Measured analytical voice that foregrounds evidence, risk, and uncertainty.",
        writing_rules=["separate evidence from inference", "state material limitations"],
        preferred_skills=["publishability-review"],
        forbidden_style_patterns=["hype", "direct buy or sell language"],
    ),
    "personal_blog": ToneProfile(
        id="personal_blog",
        label="Personal Blog",
        description="Warm first-person editorial voice without invented experience.",
        writing_rules=["sound conversational", "use first person only for editorial judgment"],
        preferred_skills=["personal-blog-voice"],
        forbidden_style_patterns=["invented anecdotes", "fake hands-on claims"],
    ),
    "luxury_premium": ToneProfile(
        id="luxury_premium",
        label="Luxury / Premium",
        description="Refined sensory language grounded in supplied evidence.",
        writing_rules=["use precise sensory vocabulary", "keep the prose restrained"],
        preferred_skills=["beauty-fragrance-writing"],
        forbidden_style_patterns=["purple prose", "invented notes or materials"],
    ),
    "seo_neutral": ToneProfile(
        id="seo_neutral",
        label="SEO Neutral",
        description="Clear, search-friendly prose with minimal stylistic ornament.",
        writing_rules=["front-load useful information", "use descriptive headings"],
        preferred_skills=["blog-post-seo-writing"],
        forbidden_style_patterns=["keyword stuffing", "clickbait"],
    ),
}


def resolve_tone_profile(tone_profile_id: str | None, domain: str) -> ToneProfile:
    """Resolve an explicit profile or infer a domain-safe default."""
    if tone_profile_id and tone_profile_id in _PROFILES:
        return _PROFILES[tone_profile_id].model_copy(deep=True)
    inferred = {
        "beauty_fragrance": "editorial_magazine",
        "beauty_makeup": "editorial_magazine",
        "fashion_lifestyle": "editorial_magazine",
        "consumer_products": "practical_buying_guide",
        "software_tools": "practical_buying_guide",
        "finance": "expert_analyst",
    }.get(domain, "seo_neutral")
    return _PROFILES[inferred].model_copy(deep=True)
