"""Conservative deterministic repair for candidate-locked articles."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from blogagent.tools.candidate_pack import CandidatePack, CandidatePackItem
from blogagent.workflow.query_contract import QueryContract


class RepairResult(BaseModel):
    repaired_markdown: str
    repair_applied: bool
    restored_candidate_ids: list[str] = Field(default_factory=list)
    remaining_issues: list[str] = Field(default_factory=list)
    repair_summary: list[str] = Field(default_factory=list)


def repair_locked_recommendation_article(
    article_markdown: str,
    candidate_pack: CandidatePack | dict,
    query_contract: QueryContract | dict,
) -> RepairResult:
    pack = (
        candidate_pack
        if isinstance(candidate_pack, CandidatePack)
        else CandidatePack.model_validate(candidate_pack)
    )
    contract = (
        query_contract
        if isinstance(query_contract, QueryContract)
        else QueryContract.model_validate(query_contract)
    )
    if contract.task_type != "recommendation" or pack.status == "not_applicable":
        return RepairResult(repaired_markdown=article_markdown, repair_applied=False)
    if pack.status == "below_minimum":
        return _repair_below_minimum(article_markdown, pack)

    original = article_markdown
    repaired = article_markdown.strip()
    summaries: list[str] = []
    restored: list[str] = []

    repaired, h1_changed = _repair_h1(repaired, pack)
    if h1_changed:
        summaries.append(f"Rewrote H1 to declare {pack.final_target_count} recommendations.")

    old_quick_ids = set(_candidate_ids_in_text(_quick_picks_body(repaired), pack))
    repaired, quick_changed = _replace_quick_picks(repaired, pack)
    if quick_changed:
        summaries.append("Rebuilt Quick Picks from the locked CandidatePack.")
        restored.extend(cid for cid in pack.locked_candidate_ids if cid not in old_quick_ids)

    if (
        pack.status == "evidence_limited"
        and contract.recommendation_strictness != "editorial"
        and not _has_limited_explanation(repaired)
    ):
        explanation = (
            f"The available evidence supported {pack.final_target_count} validated options, "
            f"rather than the {pack.requested_count} originally requested."
        )
        repaired = _insert_after_h1(repaired, explanation)
        summaries.append("Added evidence-limited framing.")

    repaired, removed_titles = _remove_extra_detail_sections(repaired, pack)
    if removed_titles:
        summaries.append(
            "Removed recommendation section(s) not in the locked CandidatePack: "
            + ", ".join(removed_titles[:3])
        )

    for index, item in enumerate(pack.items, start=1):
        if _has_detail_heading(repaired, item):
            continue
        repaired = _append_detail_section(repaired, item, index)
        restored.append(item.candidate_id)
        summaries.append(f"Restored detail section for {item.display_name}.")

    remaining = _remaining_issues(repaired, pack)
    return RepairResult(
        repaired_markdown=repaired.strip(),
        repair_applied=repaired.strip() != original.strip(),
        restored_candidate_ids=list(dict.fromkeys(restored)),
        remaining_issues=remaining,
        repair_summary=summaries,
    )


def _repair_below_minimum(markdown: str, pack: CandidatePack) -> RepairResult:
    # The repaired evidence report replaces the placeholder-based initial report.
    lower = markdown.lower()
    if "why this needs revision" in lower and "[...]" not in markdown:
        return RepairResult(repaired_markdown=markdown, repair_applied=False)
    candidates = "\n".join(f"- {_candidate_line(item)}" for item in pack.items)
    if not candidates:
        candidates = "- No candidates passed validation."
    repaired = (
        f"# Evidence Report: Draft Only\n\n"
        "## What Was Searched\n\n"
        "A bounded source search was run and each candidate was checked against "
        "this article's requirements.\n\n"
        "## Validated Candidates Found\n\n"
        f"{candidates}\n\n"
        "## Why This Needs Revision\n\n"
        f"Only {pack.final_target_count} candidates passed validation; "
        f"the minimum publishable count is {pack.minimum_publishable_items}.\n\n"
        "## What Evidence Is Missing\n\n"
        "Additional independent source support and complete candidate evidence are required.\n\n"
        "## Suggested Next Search or Refinement\n\n"
        "Narrow the use case or search stronger editorial sources before drafting a list article."
    )
    return RepairResult(
        repaired_markdown=repaired,
        repair_applied=repaired.strip() != markdown.strip(),
        repair_summary=["Converted output to a below-minimum draft-only evidence report."],
    )


def _repair_h1(markdown: str, pack: CandidatePack) -> tuple[str, bool]:
    match = re.search(r"^#\s+(.+)$", markdown, re.MULTILINE)
    current = match.group(1) if match else ""
    topic_text = re.sub(
        r"^\d+\s+(?:source-backed\s+)?(?:picks|recommendations|best)\s+(?:for\s+)?",
        "",
        current,
        flags=re.IGNORECASE,
    ).strip()
    topic_text = topic_text or "Standout Options"
    label = (
        "Our Picks"
        if pack.recommendation_strictness == "editorial"
        else "Recommended Options"
    )
    desired = f"# {pack.final_target_count} {label} for {topic_text}"
    if match:
        existing_line = match.group(0)
        if _declared_count(existing_line) == pack.final_target_count:
            return markdown, False
        return markdown[: match.start()] + desired + markdown[match.end() :], True
    return desired + "\n\n" + markdown, True


def _replace_quick_picks(markdown: str, pack: CandidatePack) -> tuple[str, bool]:
    body = "\n".join(f"- {_candidate_line(item)}" for item in pack.items)
    section = f"## Quick Picks\n\n{body}\n\n"
    match = re.search(
        r"^#{1,3}\s+Quick\s+Picks\s*$\n.*?(?=^#{1,3}\s+|\Z)",
        markdown,
        re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    if match:
        current = match.group(0).strip()
        desired = section.strip()
        if current == desired:
            return markdown, False
        return markdown[: match.start()] + section + markdown[match.end() :].lstrip(), True
    insertion = _after_intro_index(markdown)
    return markdown[:insertion].rstrip() + "\n\n" + section + markdown[insertion:].lstrip(), True


def _candidate_line(item: CandidatePackItem) -> str:
    if item.source_url:
        title = item.source_title or item.display_name
        return f"{item.display_name} ([{title}]({item.source_url}))"
    return item.display_name


def _append_detail_section(markdown: str, item: CandidatePackItem, index: int) -> str:
    context = ", ".join(item.supported_context[:2] or item.evidence_terms[:2])
    best_for = context or "a clear use case"
    evidence = _short_evidence(item)
    citation = (
        f" [{item.source_title or 'Source'}]({item.source_url})"
        if item.source_url
        else ""
    )
    section = (
        f"\n\n## {index}. {item.section_heading}\n\n"
        f"**Best for:** {best_for}\n\n"
        f"{evidence}{citation}\n\n"
        + (
            "This is an editorial pick; verify any objective details before publication."
            if item.candidate_basis in {"editorial_discretion", "weak_signal"}
            else "Check the linked source for additional context."
        )
    )
    final_match = re.search(r"^##\s+Final\s+Takeaway.*$", markdown, re.IGNORECASE | re.MULTILINE)
    if final_match:
        return (
            markdown[: final_match.start()].rstrip()
            + section
            + "\n\n"
            + markdown[final_match.start() :]
        )
    return markdown.rstrip() + section


def _short_evidence(item: CandidatePackItem) -> str:
    if item.evidence_spans:
        span = re.sub(r"\s+", " ", item.evidence_spans[0]).strip()
        if len(span) > 240:
            span = span[:237].rsplit(" ", 1)[0] + "..."
        return span
    terms = ", ".join(item.evidence_terms[:3])
    if terms:
        return f"The available evidence associates this candidate with {terms}."
    return "The available source identifies this as a validated candidate."


def _remaining_issues(markdown: str, pack: CandidatePack) -> list[str]:
    issues: list[str] = []
    if len(_candidate_ids_in_text(_quick_picks_body(markdown), pack)) != pack.final_target_count:
        issues.append("Quick Picks does not contain every locked candidate.")
    missing = [item.display_name for item in pack.items if not _has_detail_heading(markdown, item)]
    if missing:
        issues.append("Missing detail sections: " + ", ".join(missing))
    if _declared_count(markdown) != pack.final_target_count:
        issues.append("H1 count does not match CandidatePack.final_target_count.")
    if (
        pack.status == "evidence_limited"
        and pack.recommendation_strictness != "editorial"
        and not _has_limited_explanation(markdown)
    ):
        issues.append("Evidence-limited explanation is missing.")
    extras = _extra_detail_section_titles(markdown, pack)
    if extras:
        issues.append(
            "Article contains recommendation section(s) not in the locked CandidatePack: "
            + ", ".join(extras[:3])
        )
    return issues


# Numbered H2/H3 "detail section" heading + body, up to the next heading or end of text.
_NUMBERED_SECTION_RE = re.compile(
    r"^#{2,3}\s+\d+[.)]\s+(.+?)\s*\n(.*?)(?=\n#{1,3}\s+|\Z)",
    re.MULTILINE | re.DOTALL,
)


def _matches_pack_item(heading_norm: str, pack: CandidatePack) -> bool:
    if not heading_norm:
        return False
    for item in pack.items:
        for candidate in (_norm(item.display_name), _norm(item.canonical_name)):
            if not candidate:
                continue
            if heading_norm == candidate:
                return True
            if len(heading_norm) > 5 and len(candidate) > 5 and (
                heading_norm in candidate or candidate in heading_norm
            ):
                return True
    return False


def _extra_detail_section_titles(markdown: str, pack: CandidatePack) -> list[str]:
    return [
        match.group(1).strip()
        for match in _NUMBERED_SECTION_RE.finditer(markdown)
        if not _matches_pack_item(_norm(match.group(1).strip()), pack)
    ]


def _remove_extra_detail_sections(markdown: str, pack: CandidatePack) -> tuple[str, list[str]]:
    """Remove numbered recommendation sections that do not match a locked candidate."""
    removed: list[str] = []

    def repl(match: re.Match) -> str:
        heading_text = match.group(1).strip()
        if _matches_pack_item(_norm(heading_text), pack):
            return match.group(0)
        removed.append(heading_text)
        return ""

    new_markdown = _NUMBERED_SECTION_RE.sub(repl, markdown)
    if removed:
        new_markdown = re.sub(r"\n{3,}", "\n\n", new_markdown)
    return new_markdown, removed


def _quick_picks_body(markdown: str) -> str:
    match = re.search(
        r"^#{1,3}\s+Quick\s+Picks\s*$\n(.*?)(?=^#{1,3}\s+|\Z)",
        markdown,
        re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    return match.group(1) if match else ""


def _candidate_ids_in_text(text: str, pack: CandidatePack) -> list[str]:
    norm = _norm(text)
    return [
        item.candidate_id
        for item in pack.items
        if _norm(item.display_name) in norm or _norm(item.canonical_name) in norm
    ]


def _has_detail_heading(markdown: str, item: CandidatePackItem) -> bool:
    headings = re.findall(r"^#{2,3}\s+(.+)$", markdown, re.MULTILINE)
    name = _norm(item.display_name)
    canonical = _norm(item.canonical_name)
    for heading in headings:
        clean = re.sub(r"^\d+[.)]?\s*", "", _norm(heading))
        if name in clean or canonical in clean or clean in {name, canonical}:
            return True
    return False


def _insert_after_h1(markdown: str, text: str) -> str:
    match = re.search(r"^#\s+.+$", markdown, re.MULTILINE)
    if not match:
        return text + "\n\n" + markdown
    return markdown[: match.end()] + "\n\n" + text + markdown[match.end() :]


def _after_intro_index(markdown: str) -> int:
    first_h2 = re.search(r"^##\s+", markdown, re.MULTILINE)
    return first_h2.start() if first_h2 else len(markdown)


def _declared_count(text: str) -> int | None:
    match = re.search(r"^#\s+.*?\b(\d{1,3})\b", text, re.MULTILINE)
    return int(match.group(1)) if match else None


def _has_limited_explanation(markdown: str) -> bool:
    lower = markdown.lower()
    return any(
        phrase in lower
        for phrase in (
            "available evidence supported",
            "evidence supported",
            "sources supported",
            "rather than the",
            "evidence-limited",
        )
    )


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
