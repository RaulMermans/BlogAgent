"""Skill spec definitions — name and compressed runtime brief for each skill.

These briefs are injected into agent prompts to guide LLM behavior.
Keep each brief to 1-3 lines; do not dump full documentation into prompts.
"""

from __future__ import annotations

SKILL_SPECS: dict[str, dict[str, str]] = {
    "source-quality-assessment": {
        "name": "source-quality-assessment",
        "brief": (
            "Score sources by authority: high=editorial/expert/official pages, "
            "medium=niche blogs/retailer guides, "
            "low=Quora/Reddit/Instagram/TikTok/Pinterest/forums. "
            "Low-authority sources may inform context but must not dominate."
        ),
    },
    "recommendation-writing": {
        "name": "recommendation-writing",
        "brief": (
            "Write ranked recommendation articles: respect EXACT requested count "
            "(e.g. 'top 10' → exactly 10 items), use only named products/entities "
            "found in the evidence table, include Quick Picks / How We Chose / "
            "individual recommendations / choosing tips / final takeaway. "
            "If evidence supports fewer than requested, produce fewer and explain why."
        ),
    },
    "editorial-revision": {
        "name": "editorial-revision",
        "brief": (
            "Fix defects from the quality report directly: remove repetition, "
            "avoid preserving bad structure, do not invent evidence, "
            "improve readability and specificity. "
            "Do not preserve content that is generic, repeated, or unsupported."
        ),
    },
    "seo-blog-writing": {
        "name": "seo-blog-writing",
        "brief": (
            "SEO: title must match intent; meta description concise and useful "
            "(<=160 chars); avoid keyword stuffing; headings specific and descriptive; "
            "intro hooks the reader. Aim for scannable structure with clear H2/H3 sections."
        ),
    },
    "citation-grounding": {
        "name": "citation-grounding",
        "brief": (
            "Every named product, statistic, or recommendation must appear in "
            "the evidence table. Claims about notes, longevity, price, or use case "
            "require source support. Unsupported details become labelled caveats or "
            "are removed."
        ),
    },
    "financial-safety": {
        "name": "financial-safety",
        "brief": (
            "Financial content rules: no direct buy/sell advice; educational framing only; "
            "include 'not financial advice' disclaimer near top; "
            "avoid performance predictions; discuss evaluation criteria and risks only."
        ),
    },
    "beauty-fragrance-writing": {
        "name": "beauty-fragrance-writing",
        "brief": (
            "Fragrance articles: include scent family/notes only if evidence supports them; "
            "explain mood, occasion, and who the scent suits; "
            "include intensity/projection only if sourced; "
            "avoid vague words like 'nice' or 'perfect' without a specific reason."
        ),
    },
    "fashion-lifestyle-editorial": {
        "name": "fashion-lifestyle-editorial",
        "brief": (
            "Beauty/lifestyle/fashion: write with taste and cultural context; "
            "avoid generic SEO filler; make the piece feel curated and opinionated; "
            "connect product choices to mood, styling, occasion, and identity."
        ),
    },
    "product-recommendation-depth": {
        "name": "product-recommendation-depth",
        "brief": (
            "Each pick needs a clear use case and 'best for' context; "
            "include pros/caveats where evidence supports them; "
            "prefer fewer strong recommendations over weak filler; "
            "do not rely on low-quality sources for core picks."
        ),
    },
    "personal-blog-voice": {
        "name": "personal-blog-voice",
        "brief": (
            "Write with editorial confidence: stronger thesis, cleaner opening, "
            "more specific language, less generic phrasing. "
            "Concise, stylish, human tone — like a knowledgeable friend, not a content mill."
        ),
    },
    "publishability-review": {
        "name": "publishability-review",
        "brief": (
            "Before finalising: evaluate whether the post is good enough to publish. "
            "Flag generic phrasing, thin advice, weak flow, weak source synthesis, "
            "and lack of editorial POV."
        ),
    },
}
