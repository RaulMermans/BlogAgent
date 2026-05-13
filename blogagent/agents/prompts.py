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
