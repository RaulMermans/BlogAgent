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
    "luxury_editorial",
    "seo_neutral",
    "seo_practical",
    "minimalist",
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
        description="Polished, authoritative, concise editorial voice.",
        writing_rules=[
            "use varied rhythm",
            "lead with a specific editorial observation",
            "keep judgments concise",
        ],
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
        description="Warm, conversational, sensory voice without invented experience.",
        writing_rules=[
            "sound conversational",
            "use first person lightly and only for editorial judgment",
            "favor concrete sensory language",
        ],
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
    "luxury_editorial": ToneProfile(
        id="luxury_editorial",
        label="Luxury Editorial",
        description="Refined, elevated editorial language with aesthetic restraint.",
        writing_rules=[
            "use precise aesthetic vocabulary",
            "favor elegant sentence rhythm",
            "keep claims measured",
        ],
        preferred_skills=["beauty-fragrance-writing", "personal-blog-voice"],
        forbidden_style_patterns=["purple prose", "invented exclusivity claims"],
    ),
    "seo_neutral": ToneProfile(
        id="seo_neutral",
        label="SEO Neutral",
        description="Clear, search-friendly prose with minimal stylistic ornament.",
        writing_rules=["front-load useful information", "use descriptive headings"],
        preferred_skills=["blog-post-seo-writing"],
        forbidden_style_patterns=["keyword stuffing", "clickbait"],
    ),
    "seo_practical": ToneProfile(
        id="seo_practical",
        label="SEO Practical",
        description="Direct, skimmable, search-focused prose.",
        writing_rules=[
            "front-load the answer",
            "use descriptive headings",
            "make comparisons easy to scan",
        ],
        preferred_skills=["blog-post-seo-writing", "product-recommendation-depth"],
        forbidden_style_patterns=["keyword stuffing", "clickbait", "generic filler"],
    ),
    "minimalist": ToneProfile(
        id="minimalist",
        label="Minimalist",
        description="Short, clean, utility-first prose.",
        writing_rules=[
            "prefer short sentences",
            "remove ornamental transitions",
            "keep sections compact",
        ],
        preferred_skills=["publishability-review"],
        forbidden_style_patterns=["purple prose", "repetitive summaries"],
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
