"""Prompt templates for the Editor Agent and Fact-Check Evaluator.

These are placeholders. Replace with real prompts when connecting to an LLM API.
"""

RESEARCH_PLAN_PROMPT = """\
You are an editorial researcher. Given a blog topic, generate 5-7 targeted research questions.

Topic: {topic}

Return a JSON list of question strings.
"""

OUTLINE_PROMPT = """\
You are a senior editor. Given an evidence table, create a blog outline.

Topic: {topic}
Evidence Table:
{evidence_table}

Return a JSON object with: title, sections (list of strings), target_word_count, seo_keywords.
"""

DRAFT_PROMPT = """\
You are a blog writer. Given an outline and evidence table, write a full blog post.

Topic: {topic}
Outline: {outline}
Evidence Table:
{evidence_table}

Write the article in Markdown. Cite sources inline as [Source Title](URL).
Do not include any claims that are not supported by the evidence table.
"""

FACT_CHECK_PROMPT = """\
You are a fact-checking evaluator. Given a blog draft and evidence table, extract all factual claims.

Draft:
{draft}

Evidence Table:
{evidence_table}

Return a JSON list of claims, each with: text, importance (high/medium/low), section.
"""

REVISION_PROMPT = """\
You are a senior editor revising a blog post based on fact-check feedback.

Original draft:
{draft}

Fact-check issues:
{issues}

Revise the article to fix all unsupported high-importance claims.
Return the revised Markdown only.
"""
