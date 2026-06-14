"""Editor Agent — research planning, outline, draft, and revision.

Each function checks BLOGAGENT_USE_LLM_EDITOR:
  false (default) → deterministic mock output; safe for all tests, no API key needed.
  true            → calls the LLM client; falls back to mock if the call fails.

All public functions return LLMResult so callers can inspect:
    result.data              — the parsed output schema
    result.is_mock           — True when mock data was used
    result.configured_provider — what provider was requested
    result.provider          — what provider actually ran
    result.warning           — set when a configured live provider fell back to mock

Drafts must not invent citations. They reference source facts only from the
evidence table passed in as arguments.
"""

from __future__ import annotations

import json
import os
import re

from blogagent.agents import prompts
from blogagent.llm import client as llm_client
from blogagent.llm.schemas import (
    DraftOutput,
    LLMResult,
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

_MOCK_MODEL = "mock-1.0"
_MOCK_PROVIDER = "mock"


def _use_llm() -> bool:
    return os.getenv("BLOGAGENT_USE_LLM_EDITOR", "false").strip().lower() == "true"


def _mock_llm_result(data: object, configured_provider: str = "mock") -> LLMResult:
    """Wrap deterministic mock data in an LLMResult with no fallback warning."""
    return LLMResult(
        data=data,
        provider=_MOCK_PROVIDER,
        model=_MOCK_MODEL,
        is_mock=True,
        configured_provider=configured_provider,
    )


def _fallback_llm_result(data: object, base: LLMResult) -> LLMResult:
    """Wrap topic-specific mock data in an LLMResult that preserves fallback metadata."""
    fallback_warning = base.warning or (f"LLM call failed: {base.error}" if base.error else None)
    return LLMResult(
        data=data,
        provider=_MOCK_PROVIDER,
        model=_MOCK_MODEL,
        is_mock=True,
        configured_provider=base.configured_provider,
        warning=fallback_warning,
        error=base.error,
    )


# ---------------------------------------------------------------------------
# Research planning
# ---------------------------------------------------------------------------


def generate_research_plan(
    topic: str, is_recommendation: bool = False, skill_briefs: str = ""
) -> LLMResult:
    """Return 5 targeted research questions for the topic."""
    if not _use_llm():
        return _mock_llm_result(_mock_research_plan(topic, is_recommendation))

    if is_recommendation:
        system_prompt = prompts.RECOMMENDATION_RESEARCH_PLAN_PROMPT.format(topic=topic)
    else:
        system_prompt = prompts.RESEARCH_PLAN_PROMPT.format(topic=topic)

    if skill_briefs:
        system_prompt += f"\n\nActive editorial skills:\n{skill_briefs}"

    result = llm_client.generate_structured(
        system_prompt=system_prompt,
        user_prompt="Generate the research plan as a JSON object.",
        output_model=ResearchPlanOutput,
    )
    if result.is_mock:
        return _fallback_llm_result(_mock_research_plan(topic, is_recommendation), result)
    return result


def _mock_research_plan(topic: str, is_recommendation: bool = False) -> ResearchPlanOutput:
    if is_recommendation:
        return ResearchPlanOutput(
            research_questions=[
                f"Which specific named products or brands are most recommended for {topic}?",
                f"What selection criteria do reviewers use to evaluate options for {topic}?",
                f"Which named products appear repeatedly across credible sources for {topic}?",
                f"What real user or expert experiences exist with named options for {topic}?",
                f"What caveats or distinctions exist between named options for {topic}?",
            ]
        )
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
    is_recommendation: bool = False,
    skill_briefs: str = "",
    writer_handoff: dict | None = None,
    locked_skeleton: str = "",
    tone_profile: dict | None = None,
    query_contract: dict | None = None,
) -> LLMResult:
    """Return a structured blog outline grounded in the evidence table."""
    task_type = (query_contract or {}).get("task_type", "unknown")
    if not _use_llm():
        return _mock_llm_result(_mock_outline(topic, evidence_table, is_recommendation, task_type))

    evidence_summary = _format_evidence(evidence_table, source_scores)
    if is_recommendation:
        system_prompt = prompts.RECOMMENDATION_OUTLINE_PROMPT.format(
            topic=topic, evidence_table=evidence_summary
        )
        if writer_handoff:
            system_prompt += "\n\nSTRUCTURED WRITER HANDOFF:\n" + json.dumps(
                writer_handoff, indent=2
            )
        if locked_skeleton:
            system_prompt += f"\n\nLOCKED ARTICLE SKELETON:\n{locked_skeleton}"
    else:
        system_prompt = prompts.OUTLINE_PROMPT.format(topic=topic, evidence_table=evidence_summary)
    if skill_briefs:
        system_prompt += f"\n\nActive editorial skills:\n{skill_briefs}"
    if tone_profile:
        system_prompt += _format_tone_profile_prompt(tone_profile)

    result = llm_client.generate_structured(
        system_prompt=system_prompt,
        user_prompt="Generate the blog outline as a JSON object.",
        output_model=OutlineOutput,
    )
    if result.is_mock:
        return _fallback_llm_result(
            _mock_outline(topic, evidence_table, is_recommendation, task_type), result
        )
    return result


def _mock_outline(
    topic: str,
    evidence_table: list[EvidenceItem],
    is_recommendation: bool = False,
    task_type: str = "unknown",
) -> OutlineOutput:
    keywords = [w.lower() for w in topic.split()[:3] if len(w) > 3]
    if is_recommendation:
        sections = [
            "Quick Picks",
            "How We Chose",
            f"Best Options for {topic}",
            "Buying or Choosing Tips",
            "Final Takeaway",
        ]
        return OutlineOutput(
            title=f"Best {topic}: A Source-Grounded Guide",
            sections=sections,
            target_word_count=1200,
            seo_keywords=keywords or [topic.lower()],
        )
    if task_type == "how_to":
        sections = [
            "Introduction",
            "Step 1: Know What You're Looking For",
            "Step 2: Compare Your Options",
            "Step 3: Test and Decide",
            "Key Facts",
            "Conclusion",
        ]
        title = topic[:1].upper() + topic[1:] if topic else topic
        return OutlineOutput(
            title=title,
            sections=sections,
            target_word_count=900,
            seo_keywords=keywords or [topic.lower()],
        )
    sections = ["Introduction", "Key Facts", "Recent Developments", "Conclusion"]
    real_items = [e for e in evidence_table if e.confidence > 0.3]
    if real_items:
        sections = ["Introduction", "Background", "Key Facts", "Recent Developments", "Conclusion"]
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
    is_recommendation: bool = False,
    is_financial: bool = False,
    skill_briefs: str = "",
    query_contract: dict | None = None,
    allowed_recommendations: list[dict] | None = None,
    rejected_candidates: list[dict] | None = None,
    evidence_limited_mode: bool = False,
    source_quality_scores: list[dict] | None = None,
    writer_handoff: dict | None = None,
    candidate_pack: dict | None = None,
    locked_skeleton: str = "",
    tone_profile: dict | None = None,
) -> LLMResult:
    """Write a full article draft grounded in the evidence table.

    In mock mode the draft is substantive prose (not placeholder text) so
    tests and evals can check structure and non-emptiness. It does not
    invent citations; it references only facts present in evidence_table.
    """
    if not _use_llm():
        return _mock_llm_result(
            _mock_draft(
                topic,
                outline,
                evidence_table,
                is_recommendation,
                is_financial,
                allowed_recommendations=allowed_recommendations or [],
                query_contract=query_contract or {},
                evidence_limited_mode=evidence_limited_mode,
                candidate_pack=candidate_pack,
                task_type=(query_contract or {}).get("task_type", "unknown"),
            )
        )

    evidence_summary = _format_evidence(evidence_table, source_scores)
    if is_recommendation:
        system_prompt = prompts.RECOMMENDATION_DRAFT_PROMPT.format(
            topic=topic,
            outline=_format_outline(outline),
            evidence_table=evidence_summary,
        )
        system_prompt += _format_query_contract_prompt(
            query_contract or {},
            allowed_recommendations or [],
            rejected_candidates or [],
            evidence_limited_mode,
            source_quality_scores or [],
        )
        if writer_handoff:
            system_prompt += "\n\nSTRUCTURED WRITER HANDOFF:\n" + json.dumps(
                writer_handoff, indent=2
            )
        if locked_skeleton:
            system_prompt += (
                "\n\nLOCKED ARTICLE SKELETON — write inside this structure:\n" + locked_skeleton
            )
        if is_financial:
            system_prompt += prompts.FINANCIAL_DRAFT_ADDENDUM
    else:
        system_prompt = prompts.DRAFT_PROMPT.format(
            topic=topic,
            outline=_format_outline(outline),
            evidence_table=evidence_summary,
        )
        if is_financial:
            system_prompt += prompts.FINANCIAL_DRAFT_ADDENDUM

    if skill_briefs:
        system_prompt += f"\n\nActive editorial skills:\n{skill_briefs}"
    if tone_profile:
        system_prompt += _format_tone_profile_prompt(tone_profile)

    result = llm_client.generate_structured(
        system_prompt=system_prompt,
        user_prompt=(
            "Write the full article as a JSON object with "
            "article_markdown, meta_description, seo_keywords, recommended_entities, "
            "locked_entities_used, and handoff_notes."
        ),
        output_model=DraftOutput,
    )
    if result.is_mock:
        return _fallback_llm_result(
            _mock_draft(
                topic,
                outline,
                evidence_table,
                is_recommendation,
                is_financial,
                allowed_recommendations=allowed_recommendations or [],
                query_contract=query_contract or {},
                evidence_limited_mode=evidence_limited_mode,
                candidate_pack=candidate_pack,
                task_type=(query_contract or {}).get("task_type", "unknown"),
            ),
            result,
        )
    return result


def _mock_draft(
    topic: str,
    outline: OutlineOutput,
    evidence_table: list[EvidenceItem],
    is_recommendation: bool = False,
    is_financial: bool = False,
    allowed_recommendations: list[dict] | None = None,
    query_contract: dict | None = None,
    evidence_limited_mode: bool = False,
    candidate_pack: dict | None = None,
    task_type: str = "unknown",
) -> DraftOutput:
    """Generate substantive mock prose using the outline and evidence."""
    if is_recommendation:
        return _mock_recommendation_draft(
            topic,
            outline,
            evidence_table,
            is_financial,
            allowed_recommendations=allowed_recommendations or [],
            query_contract=query_contract or {},
            evidence_limited_mode=evidence_limited_mode,
            candidate_pack=candidate_pack,
        )

    lines: list[str] = [f"# {outline.title}", ""]

    if is_financial:
        lines.append(
            "> **Disclaimer**: This article is for educational purposes only and does not "
            "constitute financial advice. Consult a qualified financial adviser before making "
            "investment decisions."
        )
        lines.append("")

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

    if task_type == "how_to":
        topic_sentence = topic[:1].upper() + topic[1:] if topic else topic
        mock_body = {
            **mock_body,
            "Introduction": (
                f"{topic_sentence} comes down to a handful of practical decisions. "
                f"This guide walks through the process step by step, drawing on the "
                f"available source material so each recommendation is grounded in evidence."
            ),
            "Step 1: Know What You're Looking For": (
                "Start by writing down your priorities — budget, intended use, and any "
                "must-have features. Settling these up front keeps the rest of the "
                "process focused and saves time later."
            ),
            "Step 2: Compare Your Options": (
                "Line up the candidates that meet your priorities and compare them "
                "side by side. Reviews, comparison guides, and the source material "
                "referenced below can help narrow a long list down to a short one."
            ),
            "Step 3: Test and Decide": (
                "Where possible, try before you commit — a sample, a trial, or an "
                "in-person look can reveal details that descriptions alone miss. "
                "Pick the option that best matches the priorities you started with."
            ),
            "Key Facts": (
                f"A few facts are worth keeping in mind when thinking about {topic}. "
                f"Multiple sources converge on the practical factors that matter most."
            ),
            "Conclusion": (
                f"Working through these steps turns a decision about {topic} into a "
                f"manageable process. Revisit your priorities if nothing on the "
                f"shortlist feels right — it's better to keep looking than to settle."
            ),
        }

    for section in outline.sections:
        lines.append(f"## {section}")
        lines.append("")
        body = mock_body.get(section, f"{section} covers an important dimension of {topic}.")
        lines.append(body)
        if section in ("Key Facts", "Background"):
            for item in evidence_table[:2]:
                if item.confidence > 0:
                    lines.append(f"\nAccording to *{item.source_title}*: {item.fact}")
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


def _mock_recommendation_draft(
    topic: str,
    outline: OutlineOutput,
    evidence_table: list[EvidenceItem],
    is_financial: bool = False,
    allowed_recommendations: list[dict] | None = None,
    query_contract: dict | None = None,
    evidence_limited_mode: bool = False,
    candidate_pack: dict | None = None,
) -> DraftOutput:
    """Mock draft for recommendation-style topics.

    Does NOT invent product names. If real source facts are available they are
    referenced; otherwise the article states that real search is needed.
    """
    if candidate_pack:
        return _mock_candidate_locked_draft(topic, candidate_pack, is_financial)
    allowed_recommendations = allowed_recommendations or []
    query_contract = query_contract or {}
    requested_count = query_contract.get("requested_count")
    editorial = query_contract.get("recommendation_strictness") == "editorial"
    has_allowed = bool(allowed_recommendations)
    if evidence_limited_mode and requested_count and has_allowed:
        title = (
            f"{len(allowed_recommendations)} Our Picks for {_recommendation_subject(topic)}"
            if editorial
            else f"{len(allowed_recommendations)} Source-Backed Picks for {topic}"
        )
    else:
        title = outline.title
    lines: list[str] = [f"# {title}", ""]

    if is_financial:
        lines.append(
            "> **Disclaimer**: This article is for educational purposes only and does not "
            "constitute financial advice. Consult a qualified financial adviser before making "
            "investment decisions."
        )
        lines.append("")

    # Detect whether evidence contains real (non-template) facts
    real_items = [e for e in evidence_table if not e.fact.startswith("Information about")]
    has_real_evidence = bool(real_items)

    lines.append("## Quick Picks")
    lines.append("")
    if has_allowed:
        target_count = len(allowed_recommendations)
        if requested_count and len(allowed_recommendations) >= requested_count:
            target_count = requested_count
        draft_candidates = allowed_recommendations[:target_count]

        if requested_count and len(draft_candidates) < requested_count:
            if editorial:
                lines.append(
                    f"We narrowed this to {len(draft_candidates)} standout options, "
                    "each with a clear reason to make the list."
                )
            else:
                lines.append(
                    f"We set out to find {requested_count} recommendations, but the available "
                    f"sources only supported {len(draft_candidates)} specific products "
                    "with confidence."
                )
            lines.append("")
        lines.append("Our picks:" if editorial else "The supported picks are:")
        for cand in draft_candidates:
            # Support EntityCandidate (canonical_name) and RecommendationCandidate (name) dicts
            cand_name = (
                cand.get("canonical_name") or cand.get("name") or cand.get("raw_mention") or ""
            ).strip()
            context = cand.get("supported_context") or cand.get("evidence_terms") or []
            context_text = f" — best for {context[0]}" if context else ""
            urls = cand.get("source_urls") or []
            title_ref = (cand.get("source_titles") or ["source evidence"])[0]
            citation = f" ([{title_ref}]({urls[0]}))" if urls else ""
            lines.append(f"- {cand_name}{context_text}{citation}")
    elif has_real_evidence:
        lines.append("Based on available sources, the following were identified:")
        for item in real_items[:5]:
            lines.append(
                f"- See [{item.source_title}]({item.source_url}) for specific recommendations"
            )
    else:
        lines.append(
            "The available sources did not provide enough specific named recommendations. "
            "Enable real search (`BLOGAGENT_SEARCH_PROVIDER=tavily`) and a real LLM provider "
            "to get source-grounded, named recommendations for this topic."
        )
    lines.append("")

    lines.append("## How We Chose")
    lines.append("")
    if has_real_evidence:
        lines.append(
            f"The following selection criteria were applied when reviewing sources for {topic}: "
            "relevance to the use case, credibility of the publishing source, recency of the "
            "information, and breadth of coverage across independent reviewers."
        )
    else:
        lines.append(
            f"Selection criteria for {topic} would typically include expert consensus, "
            "user experience data, and independent review coverage. "
            "Real source data is needed to apply these criteria to specific options."
        )
    lines.append("")

    # Include remaining outline sections with substantive but non-inventive content
    handled = {"Quick Picks", "How We Chose"}
    for section in outline.sections:
        if section in handled:
            continue
        lines.append(f"## {section}")
        lines.append("")
        if has_allowed and section.lower().startswith("best"):
            for cand in draft_candidates:
                cand_name = (
                    cand.get("canonical_name") or cand.get("name") or cand.get("raw_mention") or ""
                ).strip()
                terms = cand.get("evidence_terms") or cand.get("supported_context") or []
                best_for = ", ".join(terms[:2]) if terms else "a clear use case"
                urls = cand.get("source_urls") or []
                title_ref = (cand.get("source_titles") or ["source evidence"])[0]
                citation = f" [{title_ref}]({urls[0]})" if urls else ""
                lines.append(f"### {cand_name}")
                lines.append("")
                lines.append(f"- **Name**: {cand_name}")
                lines.append(f"- **Best for**: {best_for}")
                lines.append(
                    (
                        f"- **Why we like it**: It is a specific option that fits "
                        f"{topic}.{citation}"
                        if editorial
                        else "- **Why it works**: The sources mention this product "
                        f"in the context of {topic}.{citation}"
                    )
                )
                if cand.get("confidence") != "high":
                    lines.append(
                        (
                            "- **Editorial note**: Confirm current availability and any "
                            "objective product details before use."
                            if editorial
                            else (
                                "- **Caveat**: Source support is limited; review before use."
                            )
                        )
                    )
                lines.append("")
        elif section == "Final Takeaway":
            lines.append(
                (
                    f"Use this shortlist as a starting point for {topic}, then choose "
                    "the option that best fits your priorities."
                    if editorial
                    else f"For a complete sourced list of specific recommendations on {topic}, "
                    "connect a real search provider and a real LLM provider."
                )
            )
        elif section == "Buying or Choosing Tips":
            lines.append(
                f"When evaluating options for {topic}, consider your specific use case, "
                "budget, and the credibility of the sources behind any recommendation. "
                "Cross-reference multiple independent reviews before deciding."
            )
        else:
            if has_real_evidence:
                for item in real_items[:2]:
                    excerpt = item.fact[:200]
                    lines.append(
                        f"According to [{item.source_title}]({item.source_url}): {excerpt}"
                    )
            else:
                lines.append(
                    f"{section} covers an important dimension of {topic}. "
                    "Specific details require real source evidence."
                )
        lines.append("")

    article_md = "\n".join(lines).strip()
    keywords = list(outline.seo_keywords) or [topic.lower()]
    meta = (
        f"Explore our standout picks for {topic}, with clear use cases and choosing tips."
        if editorial
        else f"A sourced guide to the best options for {topic}."
    )
    return DraftOutput(
        article_markdown=article_md,
        meta_description=meta,
        seo_keywords=keywords,
        recommended_entities=[
            {
                "candidate_id": c.get("candidate_id", ""),
                "name": (c.get("canonical_name") or c.get("name") or c.get("raw_mention") or ""),
                "section_heading": (
                    c.get("canonical_name") or c.get("name") or c.get("raw_mention") or None
                ),
                "source_url": (c.get("source_urls") or [None])[0],
            }
            for c in (draft_candidates if has_allowed else [])
            if (c.get("canonical_name") or c.get("name") or c.get("raw_mention"))
        ],
        locked_entities_used=[
            c.get("candidate_id", "")
            for c in (draft_candidates if has_allowed else [])
            if c.get("candidate_id")
        ],
    )


def _mock_candidate_locked_draft(
    topic: str,
    candidate_pack: dict,
    is_financial: bool,
) -> DraftOutput:
    """Produce a deterministic article that exactly follows CandidatePack."""
    from blogagent.tools.candidate_pack import CandidatePack  # noqa: PLC0415
    from blogagent.tools.recommendation_article_skeleton import (  # noqa: PLC0415
        build_candidate_locked_recommendation_skeleton,
    )

    pack = CandidatePack.model_validate(candidate_pack)
    editorial = pack.recommendation_strictness == "editorial"
    if pack.status == "below_minimum":
        markdown = build_candidate_locked_recommendation_skeleton(
            {"task_type": "recommendation"},
            pack,
            topic,
        )
        return DraftOutput(
            article_markdown=markdown,
            meta_description=f"Draft-only evidence report for {topic}.",
            seo_keywords=[word.lower() for word in topic.split()[:4]],
            handoff_notes=["CandidatePack was below the minimum publishable count."],
        )

    title = (
        _editorial_recommendation_title(pack.final_target_count, topic)
        if editorial
        else _standard_recommendation_title(pack.final_target_count, topic)
    )
    lines = [f"# {title}", ""]
    if is_financial:
        lines.extend(
            [
                "> **Disclaimer**: This article is for educational purposes only and does "
                "not constitute financial advice.",
                "",
            ]
        )
    if pack.status == "evidence_limited" and not editorial:
        lines.extend(
            [
                (
                    f"The available evidence supported {pack.final_target_count} validated "
                    f"options, rather than the {pack.requested_count} originally requested."
                ),
                "",
            ]
        )
    lines.extend(["## Quick Picks", ""])
    for item in pack.items:
        citation = (
            f" ([{item.source_title or item.display_name}]({item.source_url}))"
            if item.source_url
            else ""
        )
        lines.append(f"- {item.display_name}{citation}")
    lines.extend(
        [
            "",
            "## How We Chose",
            "",
            (
                "We looked for specific, credible options with a clear reason to belong "
                "on the list, then matched each one to a distinct use case."
                if editorial
                else "Each pick passed candidate validation and has source evidence attached."
            ),
            "",
        ]
    )
    for index, item in enumerate(pack.items, start=1):
        best_for = _differentiated_best_for(index, item, topic)
        evidence = _differentiated_why_like_it(index, item, topic, editorial)
        citation = (
            f" [{item.source_title or 'Source'}]({item.source_url})" if item.source_url else ""
        )
        lines.extend(
            [
                f"## {index}. {item.section_heading}",
                "",
                f"**Best for:** {best_for}",
                "",
                f"**Why we like it:** {evidence}{citation}",
                "",
                _differentiated_closing_note(index, item, topic),
                "",
            ]
        )
    lines.extend(
        [
            "## Buying or Choosing Tips",
            "",
            (
                "Compare the fit, feel, intended use, and practical tradeoffs before choosing."
                if editorial
                else "Compare the supported use case, evidence quality, and stated caveats."
            ),
            "",
            "## Final Takeaway",
            "",
            (
                "The best choice is the one that fits your taste, context, and priorities."
                if editorial
                else "The list above reflects the candidates supported by available evidence."
            ),
        ]
    )
    return DraftOutput(
        article_markdown="\n".join(lines),
        meta_description=(
            f"Explore {pack.final_target_count} standout options for "
            f"{_recommendation_subject(topic)}, with clear use cases and choosing tips."
            if editorial
            else f"Compare {pack.final_target_count} sourced options for {topic}, "
            "with evidence-linked use cases and practical choosing guidance."
        )[:160],
        seo_keywords=[word.lower() for word in topic.split()[:4]],
        recommended_entities=[
            {
                "candidate_id": item.candidate_id,
                "name": item.display_name,
                "section_heading": item.section_heading,
                "source_url": item.source_url,
            }
            for item in pack.items
        ],
        locked_entities_used=list(pack.locked_candidate_ids),
        handoff_notes=["Candidate list and structure were generated from CandidatePack."],
    )


# ---------------------------------------------------------------------------
# Differentiated per-pick copy (avoids duplicate "Best for" / "Why" text when
# evidence context is sparse — the mock generator must not produce identical
# boilerplate for every recommendation).
# ---------------------------------------------------------------------------

_BEST_FOR_ROTATION: tuple[str, ...] = (
    "everyday use and dependable performance",
    "readers who want a standout option without overthinking it",
    "anyone prioritizing value alongside quality",
    "those who want a distinctive choice that still feels practical",
    "buyers who care about long-term satisfaction over hype",
    "readers seeking a dependable option with broad appeal",
    "those who want something that performs well in most situations",
    "buyers comparing options on both feel and function",
    "anyone who wants a well-rounded pick with few compromises",
    "readers who prioritize a clear, confident choice",
)

_WHY_LIKE_IT_ROTATION: tuple[str, ...] = (
    "It consistently comes up as a strong option in this category, and it earns "
    "that reputation through a combination of solid fundamentals and broad appeal.",
    "It strikes a balance that's hard to find — the kind of pick that holds up "
    "well once the initial excitement of a new purchase fades.",
    "It has a clear identity that sets it apart from more generic alternatives in the same space.",
    "It punches above its position, offering more than buyers might expect at first glance.",
    "It rewards a closer look — the details that matter most hold up under scrutiny.",
    "It has built a loyal following for good reason: it does the fundamentals "
    "right and adds a little extra on top.",
    "It's the kind of option that feels considered rather than rushed, "
    "and that shows in daily use.",
    "It manages to feel both familiar and distinctive — comfortable to choose, "
    "but not forgettable.",
    "It holds its own against pricier or more hyped alternatives, "
    "which says a lot about where the value really lies.",
    "It's a confident pick precisely because it doesn't try to be everything "
    "to everyone — it knows what it's for and delivers on it.",
)


_GENERIC_CONTEXT_PLACEHOLDERS = frozenset({"editorial fit", "general fit", "general use"})


def _differentiated_best_for(index: int, item: object, topic: str) -> str:
    """Return a distinct 'Best for' phrase, preferring real (non-generic) evidence context."""
    raw_terms = list(getattr(item, "supported_context", []) or []) or list(
        getattr(item, "evidence_terms", []) or []
    )
    real_terms = [t for t in raw_terms if t.strip().lower() not in _GENERIC_CONTEXT_PLACEHOLDERS]
    if real_terms:
        return ", ".join(real_terms[:2])
    return _BEST_FOR_ROTATION[(index - 1) % len(_BEST_FOR_ROTATION)]


_WHY_LIKE_IT_LEAD_INS: tuple[str, ...] = (
    "{name} earns its spot through consistent real-world performance.",
    "What makes {name} worth a look comes down to the details.",
    "{name} stands out here for a fairly simple reason.",
    "The appeal of {name} becomes clear once you spend real time with it.",
    "{name} holds its place on this list on its own merits.",
    "There's a straightforward case for {name}.",
    "{name} earns its spot the old-fashioned way — through performance.",
    "Spend a little time with {name} and the reasoning becomes obvious.",
    "{name} belongs here for reasons that go beyond first impressions.",
    "The case for {name} is simple once you look a little closer.",
)


def _differentiated_why_like_it(index: int, item: object, topic: str, editorial: bool) -> str:
    """Return a distinct 'Why we like it' reason, preferring real evidence spans.

    When falling back to rotation text (no evidence spans available), both the
    lead-in clause AND the reasoning are rotated independently by index so no
    two picks read with the same template shape — a single shared lead-in
    phrase ("X made the list because...") reads as templated to a human editor
    even when the trailing reasoning differs.
    """
    spans = getattr(item, "evidence_spans", None) or []
    if spans:
        return spans[0]
    # Prefer the reader-facing display form — canonical_name is a lowercased,
    # normalized form used for internal matching/dedup and reads as broken
    # prose if it leaks into a sentence (e.g. "dolce & gabbana ... earns its spot").
    name = (
        getattr(item, "display_name", "")
        or getattr(item, "section_heading", "")
        or getattr(item, "canonical_name", "")
    )
    base = _WHY_LIKE_IT_ROTATION[(index - 1) % len(_WHY_LIKE_IT_ROTATION)]
    if name:
        lead_in = _WHY_LIKE_IT_LEAD_INS[(index - 1) % len(_WHY_LIKE_IT_LEAD_INS)].format(name=name)
        return f"{lead_in} {base}"
    return base


_CLOSING_NOTE_ROTATION: tuple[str, ...] = (
    "If this sounds like the right fit, it's worth a closer look against the rest of the list.",
    "Weigh it against your specific priorities — the right choice often comes down to fit.",
    "It's a strong contender, but the best pick always depends on what matters most to you.",
    "Consider how it stacks up against the alternatives here before making a final call.",
    "If the points above resonate, this is a pick worth shortlisting seriously.",
    "Like any choice on this list, it rewards a little extra research before committing.",
    "It holds up well in comparison — give it real consideration alongside the others.",
    "The details here matter more than they might seem; take a moment to compare.",
    "It's earned its spot, but trust your own priorities when making the final decision.",
    "Take a moment to see how this one lines up with what you're actually looking for.",
)


def _differentiated_closing_note(index: int, item: object, topic: str) -> str:
    """Return a distinct closing sentence for each pick section."""
    return _CLOSING_NOTE_ROTATION[(index - 1) % len(_CLOSING_NOTE_ROTATION)]


def _format_query_contract_prompt(
    query_contract: dict,
    allowed_recommendations: list[dict],
    rejected_candidates: list[dict],
    evidence_limited_mode: bool,
    source_quality_scores: list[dict],
) -> str:
    """Append contract-aware drafting instructions to the recommendation prompt."""
    requested_count = query_contract.get("requested_count")
    allowed_count = len(allowed_recommendations)
    enough_candidates = allowed_count >= (requested_count or 0) if requested_count else True
    strictness = query_contract.get("recommendation_strictness", "standard")
    editorial = strictness == "editorial"

    # Build approved candidate list in clean, reader-friendly format
    allowed_lines = []
    for c in allowed_recommendations[:20]:
        cand_name = (c.get("canonical_name") or c.get("name") or c.get("raw_mention") or "").strip()
        terms = c.get("evidence_terms") or c.get("supported_context") or []
        urls = c.get("source_urls") or []
        terms_text = ", ".join(terms[:4]) if terms else ""
        url_text = urls[0] if urls else ""
        entry = f"- {cand_name}"
        if terms_text:
            entry += f" | context: {terms_text}"
        if url_text:
            entry += f" | url: {url_text}"
        allowed_lines.append(entry)

    # Build do-not-use list (name only, no internal field names)
    rejected_lines = []
    for c in rejected_candidates[:20]:
        cand_name = (c.get("canonical_name") or c.get("name") or c.get("raw_mention") or "").strip()
        if cand_name:
            rejected_lines.append(f"- {cand_name}")

    # Count instructions
    if requested_count and enough_candidates:
        count_rule = (
            f"- APPROVED LIST has {allowed_count} items; topic requests {requested_count}.\n"
            f"- You MUST include exactly {requested_count} items from the approved list.\n"
            "- Including fewer than the requested count is a contract failure.\n"
        )
    elif requested_count and not enough_candidates and editorial:
        count_rule = (
            f"- Only {allowed_count} picks are available for this topic.\n"
            f"- Write a focused article around {allowed_count} picks.\n"
            "- Open naturally: e.g., 'After reviewing the options, these stood out.'\n"
            "- Do NOT mention counts being reduced or any pipeline language.\n"
        )
    elif requested_count and not enough_candidates:
        count_rule = (
            f"- Only {allowed_count} items available (requested: {requested_count}).\n"
            f"- Include all {allowed_count} items and add one natural sentence explaining "
            "why the article covers fewer options.\n"
        )
    else:
        count_rule = ""

    editorial_voice_rule = (
        (
            "- Write in confident, natural editorial voice: 'our picks', 'worth considering',\n"
            "  'why we like it', 'stands out for'. Avoid clinical language.\n"
            "- Do NOT write: 'source-backed', 'evidence-limited', 'validated candidates',\n"
            "  'query contract', 'candidate pack', 'evidence table', 'allowed list',\n"
            "  'rigorous evidence', 'passage from the source', or 'not explicitly mentioned'.\n"
            "- If editorial discretion shaped the list, phrase it naturally:\n"
            "  'Our picks balance reputation, availability, and editorial judgment.'\n"
        )
        if editorial
        else (
            "- If the count is reduced, state the limitation plainly without pipeline jargon.\n"
            "- Do NOT write internal field names or QA phrases in the article.\n"
        )
    )

    return (
        "\n\nAPPROVED PICKS — write ONLY about items from this list:\n"
        + ("\n".join(allowed_lines) if allowed_lines else "- none\n")
        + "\n\nDO NOT RECOMMEND (excluded from this article):\n"
        + ("\n".join(rejected_lines) if rejected_lines else "- none\n")
        + f"\n\nARTICLE CONTRACT (internal — do not reproduce in article):\n"
        f"- Approved item count: {allowed_count}\n"
        f"- Requested count: {requested_count}\n"
        "\n\nDRAFTING RULES (MANDATORY):\n"
        "- ONLY recommend items from the APPROVED PICKS list above. No exceptions.\n"
        "- Do not introduce any product, brand, or entity not in the approved list.\n"
        "- Do not turn source titles, section headings, or authors into recommendations.\n"
        + count_rule
        + "- Every pick needs: a distinct 'Best for', a clear reason, useful context.\n"
        "- Include a Quick Picks section listing all approved picks.\n"
        "- For fragrance/perfume: include notes, mood, or occasion only if in context above.\n"
        + editorial_voice_rule
    )


def _recommendation_subject(topic: str) -> str:
    """Strip framing/count language so the title isn't a doubled-up mess.

    Some topics phrase the count as a leading qualifier ("5 best perfumes"),
    but others embed it inside a "guide to" framing ("a casual guide to the
    top 5 summer fragrances"). Naively prefixing "{count} Best {topic}: Our
    Picks" onto the latter produces nonsense like "5 Best A Casual Guide To
    The Top 5 Summer Fragrances: Our Picks". Strip both the framing phrase and
    the embedded count/qualifier so only the bare subject ("summer fragrances")
    remains, regardless of which style the user wrote in.
    """
    subject = topic.strip()
    # Drop a leading "a/an/the <adjective> guide/roundup/list to/for/on " framing
    # phrase, exposing whatever count/qualifier sits inside it.
    subject = re.sub(
        r"^\s*(?:a|an|the)?\s*[\w-]*\s*"
        r"(?:guide|roundup|round-up|rundown|list|primer)\s+(?:to|for|on)\s+",
        "",
        subject,
        flags=re.IGNORECASE,
    ).strip()
    # Drop a leading list count/qualifier — "top 5 ", "5 best ", "the top 5 best ".
    subject = re.sub(
        r"^\s*(?:the\s+)?(?:top\s+)?\d+\s+(?:best\s+)?",
        "",
        subject,
        flags=re.IGNORECASE,
    ).strip()
    return subject or topic


def _editorial_recommendation_title(count: int, topic: str) -> str:
    subject = _recommendation_subject(topic)
    if subject.lower().startswith("best "):
        subject = subject[5:].strip()
    return f"{count} Best {subject.title()}: Our Picks"


def _standard_recommendation_title(count: int, topic: str) -> str:
    subject = _recommendation_subject(topic)
    if subject.lower().startswith("best "):
        subject = subject[5:].strip()
    return f"{count} Best {subject}"


def _format_tone_profile_prompt(tone_profile: dict) -> str:
    return (
        "\n\nTONE PROFILE — voice only; never change count, candidates, citations, "
        "evidence rules, safety constraints, or status:\n" + json.dumps(tone_profile, indent=2)
    )


# ---------------------------------------------------------------------------
# Revision
# ---------------------------------------------------------------------------


def revise_article(
    topic: str,
    draft: str,
    fact_check_report: FactCheckReport,
    citation_matches: list[CitationMatch],
) -> LLMResult:
    """Revise the draft to address blocking fact-check issues."""
    if not _use_llm():
        return _mock_llm_result(_mock_revision(draft, fact_check_report))

    issues = "\n".join(fact_check_report.blocking_issues) or "No specific blocking issues listed."
    result = llm_client.generate_structured(
        system_prompt=prompts.REVISION_PROMPT.format(draft=draft, issues=issues),
        user_prompt=(
            "Revise the article and return a JSON object "
            "with revised_markdown and revision_summary."
        ),
        output_model=RevisionOutput,
    )
    if result.is_mock:
        return _fallback_llm_result(_mock_revision(draft, fact_check_report), result)
    return result


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


def _format_evidence(evidence_table: list[EvidenceItem], source_scores: list[SourceScore]) -> str:
    if not evidence_table:
        return "No evidence items available."
    score_map = {s.url: s.overall_score for s in source_scores}
    rows = []
    for item in evidence_table[:10]:  # cap at 10 to keep prompt size reasonable
        score = score_map.get(item.source_url, item.confidence)
        rows.append(f"- [{item.source_title}]({item.source_url}) (score={score:.2f}): {item.fact}")
    return "\n".join(rows)


def _format_outline(outline: OutlineOutput) -> str:
    sections = "\n".join(f"  - {s}" for s in outline.sections)
    return (
        f"Title: {outline.title}\n"
        f"Sections:\n{sections}\n"
        f"Target word count: {outline.target_word_count}\n"
        f"SEO keywords: {', '.join(outline.seo_keywords)}"
    )
