"""Editor Agent — research planning, outline, draft, and revision.

Each function checks BLOGAGENT_USE_LLM_EDITOR:
  false (default) → deterministic mock output; safe for all tests, no API key needed.
  true            → calls the LLM client; falls back to mock if the call fails.

Drafts must not invent citations. They reference source facts only from the
evidence table passed in as arguments.
"""

from __future__ import annotations

import os
import warnings

from blogagent.agents import prompts
from blogagent.llm import client as llm_client
from blogagent.llm.schemas import (
    DraftOutput,
    OutlineOutput,
    ResearchPlanOutput,
    RevisionOutput,
)
from blogagent.workflow.state import (
    CitationMatch,
    EvidenceItem,
    FactCheckReport,
    SourceScore,
)


def _use_llm() -> bool:
    return os.getenv("BLOGAGENT_USE_LLM_EDITOR", "false").strip().lower() == "true"


# ---------------------------------------------------------------------------
# Research planning
# ---------------------------------------------------------------------------


def generate_research_plan(topic: str) -> ResearchPlanOutput:
    """Return 5 targeted research questions for the topic."""
    if not _use_llm():
        return _mock_research_plan(topic)

    result = llm_client.generate_structured(
        system_prompt=prompts.RESEARCH_PLAN_PROMPT.format(topic=topic),
        user_prompt="Generate the research plan as a JSON object.",
        output_model=ResearchPlanOutput,
    )
    if result.error or result.data is None:
        warnings.warn(
            f"LLM research plan failed: {result.error or 'no data'}; using mock fallback.",
            stacklevel=2,
        )
        return _mock_research_plan(topic)
    return result.data


def _mock_research_plan(topic: str) -> ResearchPlanOutput:
    return ResearchPlanOutput(
        research_questions=[
            f"What is {topic} and why does it matter?",
            f"What are the main components or aspects of {topic}?",
            f"What recent developments have occurred in {topic}?",
            f"What are common misconceptions or debates about {topic}?",
            f"How does {topic} affect everyday life or practice?",
        ]
    )


# ---------------------------------------------------------------------------
# Outline generation
# ---------------------------------------------------------------------------


def generate_outline(
    topic: str,
    evidence_table: list[EvidenceItem],
    source_scores: list[SourceScore],
) -> OutlineOutput:
    """Return a structured blog outline grounded in the evidence table."""
    if not _use_llm():
        return _mock_outline(topic, evidence_table)

    evidence_summary = _format_evidence(evidence_table, source_scores)
    result = llm_client.generate_structured(
        system_prompt=prompts.OUTLINE_PROMPT.format(
            topic=topic, evidence_table=evidence_summary
        ),
        user_prompt="Generate the blog outline as a JSON object.",
        output_model=OutlineOutput,
    )
    if result.error or result.data is None:
        warnings.warn(
            f"LLM outline failed: {result.error or 'no data'}; using mock fallback.",
            stacklevel=2,
        )
        return _mock_outline(topic, evidence_table)
    return result.data


def _mock_outline(topic: str, evidence_table: list[EvidenceItem]) -> OutlineOutput:
    sections = ["Introduction", "Key Facts", "Recent Developments", "Conclusion"]
    # Add an Evidence section when we have real evidence items
    real_items = [e for e in evidence_table if e.confidence > 0.3]
    if real_items:
        sections = ["Introduction", "Background", "Key Facts", "Recent Developments", "Conclusion"]
    keywords = [w.lower() for w in topic.split()[:3] if len(w) > 3]
    return OutlineOutput(
        title=f"Understanding {topic}",
        sections=sections,
        target_word_count=1000,
        seo_keywords=keywords or [topic.lower()],
    )


# ---------------------------------------------------------------------------
# Draft writing
# ---------------------------------------------------------------------------


def write_article_draft(
    topic: str,
    outline: OutlineOutput,
    evidence_table: list[EvidenceItem],
    source_scores: list[SourceScore],
) -> DraftOutput:
    """Write a full article draft grounded in the evidence table.

    In mock mode the draft is substantive prose (not placeholder text) so
    tests and evals can check structure and non-emptiness. It does not
    invent citations; it references only facts present in evidence_table.
    """
    if not _use_llm():
        return _mock_draft(topic, outline, evidence_table)

    evidence_summary = _format_evidence(evidence_table, source_scores)
    result = llm_client.generate_structured(
        system_prompt=prompts.DRAFT_PROMPT.format(
            topic=topic,
            outline=_format_outline(outline),
            evidence_table=evidence_summary,
        ),
        user_prompt=(
            "Write the full article as a JSON object with "
            "article_markdown, meta_description, and seo_keywords."
        ),
        output_model=DraftOutput,
    )
    if result.error or result.data is None:
        warnings.warn(
            f"LLM draft failed: {result.error or 'no data'}; using mock fallback.",
            stacklevel=2,
        )
        return _mock_draft(topic, outline, evidence_table)
    return result.data


def _mock_draft(
    topic: str, outline: OutlineOutput, evidence_table: list[EvidenceItem]
) -> DraftOutput:
    """Generate substantive mock prose using the outline and evidence."""
    lines: list[str] = [f"# {outline.title}", ""]

    mock_body: dict[str, str] = {
        "Introduction": (
            f"{topic} is a subject that draws interest from researchers, practitioners, "
            f"and curious readers alike. This article provides an evidence-based overview "
            f"drawing on available sources."
        ),
        "Background": (
            f"The study of {topic} has a rich history. Understanding its origins and "
            f"development helps contextualise current knowledge and ongoing debates."
        ),
        "Key Facts": (
            f"Several important facts characterise {topic}. Multiple sources converge on "
            f"the significance of this area and document its major dimensions."
        ),
        "Recent Developments": (
            f"In recent years, {topic} has seen notable advances. New research, tools, "
            f"and applications continue to expand what is known and what is possible."
        ),
        "Implications": (
            f"The implications of {topic} span practice, policy, and public understanding. "
            f"Continued study is important for informed decision-making."
        ),
        "Conclusion": (
            f"This overview reflects the available evidence on {topic}. "
            f"Readers seeking further depth should consult the primary sources cited."
        ),
    }

    for section in outline.sections:
        lines.append(f"## {section}")
        lines.append("")
        body = mock_body.get(section, f"{section} covers an important dimension of {topic}.")
        lines.append(body)
        # Append evidence facts for the first two evidence items, if any
        if section in ("Key Facts", "Background"):
            for item in evidence_table[:2]:
                if item.confidence > 0:
                    lines.append(
                        f"\nAccording to *{item.source_title}*: {item.fact}"
                    )
        lines.append("")

    article_md = "\n".join(lines).strip()
    keywords = list(outline.seo_keywords) or [topic.lower()]
    meta = (
        f"An evidence-based overview of {topic}, covering key facts, "
        f"recent developments, and practical implications."
    )
    return DraftOutput(
        article_markdown=article_md,
        meta_description=meta,
        seo_keywords=keywords,
    )


# ---------------------------------------------------------------------------
# Revision
# ---------------------------------------------------------------------------


def revise_article(
    topic: str,
    draft: str,
    fact_check_report: FactCheckReport,
    citation_matches: list[CitationMatch],
) -> RevisionOutput:
    """Revise the draft to address blocking fact-check issues."""
    if not _use_llm():
        return _mock_revision(draft, fact_check_report)

    issues = "\n".join(fact_check_report.blocking_issues) or "No specific blocking issues listed."
    result = llm_client.generate_structured(
        system_prompt=prompts.REVISION_PROMPT.format(draft=draft, issues=issues),
        user_prompt=(
            "Revise the article and return a JSON object "
            "with revised_markdown and revision_summary."
        ),
        output_model=RevisionOutput,
    )
    if result.error or result.data is None:
        warnings.warn(
            f"LLM revision failed: {result.error or 'no data'}; returning draft unchanged.",
            stacklevel=2,
        )
        return _mock_revision(draft, fact_check_report)
    return result.data


def _mock_revision(draft: str, fact_check_report: FactCheckReport) -> RevisionOutput:
    issues = fact_check_report.blocking_issues
    if issues:
        summary = (
            f"Mock revision: {len(issues)} blocking issue(s) noted. "
            f"No LLM provider configured — draft returned without changes. "
            f"Issues: {'; '.join(issues[:3])}"
        )
    else:
        summary = "Mock revision: no blocking issues found. Draft returned unchanged."
    return RevisionOutput(revised_markdown=draft, revision_summary=summary)


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _format_evidence(
    evidence_table: list[EvidenceItem], source_scores: list[SourceScore]
) -> str:
    if not evidence_table:
        return "No evidence items available."
    score_map = {s.url: s.overall_score for s in source_scores}
    rows = []
    for item in evidence_table[:10]:  # cap at 10 to keep prompt size reasonable
        score = score_map.get(item.source_url, item.confidence)
        rows.append(
            f"- [{item.source_title}]({item.source_url}) "
            f"(score={score:.2f}): {item.fact}"
        )
    return "\n".join(rows)


def _format_outline(outline: OutlineOutput) -> str:
    sections = "\n".join(f"  - {s}" for s in outline.sections)
    return (
        f"Title: {outline.title}\n"
        f"Sections:\n{sections}\n"
        f"Target word count: {outline.target_word_count}\n"
        f"SEO keywords: {', '.join(outline.seo_keywords)}"
    )
