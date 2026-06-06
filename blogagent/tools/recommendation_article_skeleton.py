"""Deterministic article frames for candidate-locked recommendation writing."""

from __future__ import annotations

from blogagent.tools.candidate_pack import CandidatePack
from blogagent.workflow.query_contract import QueryContract


def build_candidate_locked_recommendation_skeleton(
    query_contract: QueryContract | dict,
    candidate_pack: CandidatePack | dict,
    topic: str,
    tone_profile: dict | None = None,
) -> str:
    contract = (
        query_contract
        if isinstance(query_contract, QueryContract)
        else QueryContract.model_validate(query_contract)
    )
    pack = (
        candidate_pack
        if isinstance(candidate_pack, CandidatePack)
        else CandidatePack.model_validate(candidate_pack)
    )
    tone_note = ""
    if tone_profile:
        tone_note = f"\n<!-- Tone: {tone_profile.get('label', tone_profile.get('id', 'Auto'))} -->"

    if pack.status == "below_minimum":
        return (
            f"# Evidence Report: {topic}\n"
            f"{tone_note}\n\n"
            "## What Was Searched\n\n[Summarize the bounded research scope.]\n\n"
            "## Candidates Found\n\n"
            + (
                "\n".join(f"- {item.display_name}" for item in pack.items)
                or "- No candidates passed validation."
            )
            + "\n\n## Why Not Publish-Ready\n\n"
            f"Only {pack.final_target_count} clean candidates were found; "
            f"the minimum is {pack.minimum_publishable_items}.\n\n"
            "## What Evidence Is Missing\n\n[Describe the missing source support.]\n\n"
            "## Suggested Next Search or Refinement\n\n"
            "[Suggest a narrower query or stronger source coverage.]"
        )

    editorial = contract.recommendation_strictness == "editorial"
    title_label = "Our Picks" if editorial else "Recommended Options"
    lines = [
        f"# {pack.final_target_count} {title_label} for {topic}",
        tone_note,
        "",
        "[Intro. Keep the locked count and candidate set unchanged.]",
        "",
    ]
    if pack.status == "evidence_limited" and not editorial:
        lines.extend(
            [
                (
                    f"The evidence supported {pack.final_target_count} validated options, "
                    f"rather than the {pack.requested_count} originally requested."
                ),
                "",
            ]
        )
    lines.extend(["## Quick Picks", ""])
    for item in pack.items:
        citation = f" ([{item.source_title}]({item.source_url}))" if item.source_url else ""
        lines.append(f"- {item.display_name}{citation}")
    selection_prompt = (
        "[Explain the editorial selection logic, use cases, and what made each option stand out.]"
        if editorial
        else "[Explain source-bound selection criteria.]"
    )
    lines.extend(["", "## How We Chose", "", selection_prompt, ""])
    for index, item in enumerate(pack.items, start=1):
        lines.extend(
            [
                f"## {index}. {item.section_heading}",
                "",
                f"**Best for:** {', '.join(item.supported_context[:2]) or 'a clear use case'}",
                "",
                (
                    "[Explain why we like it without inventing prices, specs, awards, "
                    "reviews, quotes, or objective claims.]"
                    if editorial
                    else "[Write a conservative evidence-grounded explanation.]"
                ),
                "",
            ]
        )
    lines.extend(
        [
            "## Buying or Choosing Tips",
            "",
            (
                "[Add practical choosing guidance.]"
                if editorial
                else "[Add source-grounded choosing guidance.]"
            ),
            "",
            "## Final Takeaway",
            "",
            "[Summarize the locked recommendations without adding new entities.]",
        ]
    )
    if contract.safety_constraints:
        lines.insert(
            2,
            "> **Disclaimer**: This article is for educational purposes only and does not "
            "constitute financial advice.",
        )
    return "\n".join(line for line in lines if line != "<!-- Tone: Auto -->").strip()
