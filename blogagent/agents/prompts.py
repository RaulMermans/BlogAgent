"""Prompt templates for the Editor Agent and Fact-Check Evaluator.

All prompts instruct the model to return a specific JSON structure.
The LLM client augments each prompt with the full Pydantic JSON schema
before sending — these templates set role and context only.
"""

RESEARCH_PLAN_PROMPT = """\
You are an editorial researcher. Given a blog topic, generate 5 targeted research questions.

These questions will guide web searches and source selection. Make them specific, answerable,
and grounded — not generic. Cover definition, evidence, recent developments, controversies,
and practical significance.

Topic: {topic}
"""

OUTLINE_PROMPT = """\
You are a senior editor. Given a topic and a curated evidence table, create a blog outline.

Evidence-first rule: the outline must be shaped by what the evidence table actually contains,
not by what you expect to be true about the topic. Do not plan sections that have no evidence.

Topic: {topic}

Evidence Table:
{evidence_table}

Guidelines:
- Title should be informative and SEO-friendly (not clickbait).
- 4-6 sections maximum.
- target_word_count between 800 and 1500.
- seo_keywords: 3-6 terms, all lower-case.
"""

DRAFT_PROMPT = """\
You are a blog writer. Given an outline and evidence table, write a full blog post in Markdown.

Source-grounding rules:
- Every factual claim must come from the evidence table.
- Do not include any claim that is not supported by evidence.
- Cite sources inline as [Source Title](URL) immediately after the claim.
- If a section has no evidence, write only what is definitively known and mark uncertain claims.
- If sources are marked as mock placeholders, note that the content is provisional.

Topic: {topic}

Outline:
{outline}

Evidence Table:
{evidence_table}
"""

FACT_CHECK_JUDGMENT_PROMPT = """\
You are a fact-checking evaluator. Your job is to assess a blog draft against
the available evidence and citation matches.

Rules:
- Only judge based on the provided claims, citation matches, and source scores.
- Do not invent sources or fabricate facts.
- Unsupported high-importance claims are blocking issues.
- Unsupported medium/low-importance claims are revision notes, not blockers.
- passed=true only if there are zero blocking issues.

Topic: {topic}

Draft (truncated):
{draft}

Claim and Citation Summary:
{claim_summary}

Source Quality Summary:
{source_summary}
"""

FACT_CHECK_PROMPT = """\
You are a fact-checking evaluator. Given a blog draft and topic, extract all factual claims.

Only extract claims that assert a fact about the world — ignore structural headings,
transitional sentences, and opinion phrases. Each claim should be a single, complete sentence.

Classify importance:
  high   — numerical, statistical, or comparative claim that could be disputed
  medium — general factual assertion
  low    — widely accepted background statement

Topic: {topic}

Draft:
{draft}
"""

CITATION_JUDGE_PROMPT = """\
You are a citation judge. Your only job is to determine whether the provided source excerpt
supports the given claim.

Rules:
- Judge ONLY based on the provided source excerpt. Do not use outside knowledge.
- Do not invent sources or fabricate references.
- mark supported: the excerpt clearly and directly supports the claim.
- mark partially_supported: the excerpt supports part of the claim but not all of it.
- mark unsupported: the excerpt does not clearly support the claim.
- confidence reflects how clearly the excerpt addresses the claim.

Claim: {claim}

Source URL: {source_url}

Source Excerpt:
{source_excerpt}
"""

RECOMMENDATION_RESEARCH_PLAN_PROMPT = """\
You are an editorial researcher. Given a recommendation-style blog topic, generate 5 targeted
research questions aimed at identifying SPECIFIC NAMED products, services, brands, or entities.

Your goal is NOT to describe the category in general — it is to surface the actual named
options that real sources recommend.

Research questions must:
1. Ask which specific named products or brands experts and reviewers consistently recommend.
2. Ask what selection criteria (features, performance, price, longevity, etc.) are used.
3. Ask which named options appear repeatedly across multiple credible sources.
4. Ask about real user or expert experiences with particular named products.
5. Ask about caveats, weaknesses, or important distinctions between named options.

Do NOT generate questions about the category in general. Focus on named entities that can
be cited directly from source text.

Topic: {topic}
"""

RECOMMENDATION_OUTLINE_PROMPT = """\
You are a senior editor creating a recommendation-style blog outline.

Evidence-first rule: the outline must be shaped entirely by what the evidence table actually
contains. Only plan sections for named products, services, or entities that appear in the
evidence table. Do not plan sections for anything not mentioned in the evidence.

Topic: {topic}

Evidence Table:
{evidence_table}

Required structure for recommendation posts:
  1. Quick Picks — a short bullet list of 5–10 named recommendations found in sources
  2. How We Chose — the selection criteria derived from source evidence
  3. Best [Category] for [Use Case] — individual sections per top named recommendation
  4. Buying or Choosing Tips — practical advice sourced from evidence
  5. Final Takeaway

Guidelines:
- Title must be specific and SEO-friendly; include the named category.
- The outline MUST include a "Quick Picks" section at the top.
- Only include named products or entities that appear in the evidence table.
- If the evidence table does not contain enough named products, note that and plan a reduced
  structure — do not invent names.
- target_word_count between 1000 and 2000.
- seo_keywords: 3-6 terms, all lower-case.
"""

RECOMMENDATION_DRAFT_PROMPT = """\
You are a blog writer. Given an outline and evidence table, write a recommendation-style
blog post in Markdown.

The candidate list is locked. Your task is to write inside the structure, not decide the
recommendation set.

Source-grounding rules — MANDATORY:
- You MAY ONLY name specific products, brands, or entities that appear in the evidence table.
- Do NOT invent product names, brand names, or recommendations.
- If a source mentions a named product, cite it inline: [Source Title](URL).
- If the evidence table does not contain enough named products, write exactly:
    "The available sources did not provide enough specific named recommendations."
  Do NOT invent a list.

EXACT COUNT RULE — MANDATORY:
If the topic specifies a number (e.g., "top 10", "best 5"), produce EXACTLY that many
recommendations in Quick Picks — not one more, not one less.
If the evidence table contains fewer supported items than requested, produce only what
the evidence supports and add a sentence at the end explaining why fewer items are listed.

DEDUPLICATION RULES — MANDATORY:
- No section may repeat the same text, sentence, or information from another section.
- No source excerpt may appear verbatim in more than one section.
- Every recommendation must be supported by distinct evidence from a different source excerpt.

SOURCE QUALITY RULE:
Prefer editorial, journalistic, or expert review sources. Do not use Quora, Instagram,
Reddit, or similar user-generated platforms as primary evidence when stronger sources exist.

Required article structure:

## Quick Picks
A bullet list of named recommendations (only those found in sources). Obey any explicit
count stated in the topic (e.g., "top 10" → exactly 10 bullets, not 11).

## How We Chose
Explain the selection criteria based on source evidence.

## Best [Category] for [Use Case]
For each named recommendation found in sources:
- **Name**: [product/entity name exactly as it appears in source]
- **Best for**: [specific use case]
- **Why it works**: [evidence-based reason with citation]
- **Source**: [inline citation]
- **Caveat**: [note if evidence is weak or partial]

## Buying or Choosing Tips
Practical advice from the sources.

## Final Takeaway

Topic: {topic}

Outline:
{outline}

Evidence Table:
{evidence_table}
"""

FINANCIAL_DRAFT_ADDENDUM = """\

FINANCIAL CONTENT RULES — MANDATORY:
- Do NOT recommend specific securities or assets with "buy" language.
- Frame all content as educational overview and evaluation criteria only.
- Include this disclaimer near the top of the article:
    > **Disclaimer**: This article is for educational purposes only and does not constitute
    > financial advice. Consult a qualified financial adviser before making investment decisions.
- Avoid phrases like "buy this stock", "invest in X now", or "guaranteed returns".
- Discuss evaluation criteria and general principles instead of direct recommendations.
"""

REVISION_PROMPT = """\
You are a senior editor revising a blog post based on fact-check feedback.

Revision rules:
- Remove or rewrite every unsupported high-importance claim.
- Do not add new factual claims not present in the original draft.
- Preserve well-supported content unchanged.
- Be concise in revision_summary: list what changed and why.

Original draft:
{draft}

Fact-check blocking issues:
{issues}
"""

QUALITY_REVISION_PROMPT = """\
You are a senior editor revising a blog post based on a quality evaluation report.

When a structured ReviewPacket and RevisionPlan are supplied, they are the revision contract.
Resolve listed defects, preserve every locked candidate, and report unresolved defects rather
than deleting candidates.

Quality defects to fix:
{defects}

Active editorial skills:
{skill_briefs}

Source quality context:
{source_quality_summary}

Revision constraints (MANDATORY):
- Fix each identified defect directly and completely.
- If is_recommendation={is_recommendation} and requested_count={requested_count}:
  ensure Quick Picks has EXACTLY {requested_count} named items — not more, not fewer.
- Remove any text that repeats across sections verbatim.
- Do not invent recommendations, products, or facts not supported by the evidence.
- For financial topics: preserve the "not financial advice" disclaimer at the top.
- Prefer fewer strong, evidence-backed picks over more weak ones.
- Improve readability: make headings specific, intro engaging, takeaway useful.
- Do not preserve bad structure — rewrite sections that are generic or placeholder-like.

Original draft (may be truncated to 4000 chars):
{draft}
"""

PUBLISHABILITY_EVALUATION_PROMPT = """\
You are a senior personal-blog editor evaluating whether an article is ready to publish.

Evaluate on these dimensions:
1. Intro quality — specific opening or generic filler?
2. Editorial POV — does the article have a clear opinion or thesis?
3. Recommendation depth — are picks specific with use-case context?
4. Sensory/contextual detail — does lifestyle/fragrance content include mood/occasion/notes?
5. Source synthesis — are sources woven into prose or just listed?
6. Conclusion quality — specific recommendation or generic wrap-up?
7. Title quality — specific and editorial, or generic SEO filler?

Topic: {topic}
Is recommendation: {is_recommendation}

Article (may be truncated):
{article}

Return a JSON object with:
- publish_ready: bool
- score: int (0-100)
- polish_required: bool (true when score < 80 or medium/high defects exist)
- defects: list of objects with type, severity, message
- summary: string
"""

ENRICHMENT_SEARCH_PLAN_PROMPT = """\
You are a research planner. Generate {count} targeted search queries to find more
specific named recommendations for this topic.

The initial search found only {supported_count} of the {requested_count} requested items.
Generate queries that specifically target named products, reviews, and editorial picks.

Topic: {topic}

Requirements:
- Each query should be distinct and targeted
- Focus on finding named product recommendations from editorial sources
- Include terms like "editor picks", "best", "reviews", "guide"
- Avoid generic educational queries

Return {count} search queries as a JSON list of strings.
"""
