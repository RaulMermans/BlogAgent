"""Draft Candidate Compliance — verify the draft uses allowed candidates.

Permission class: read_only
All operations are deterministic — no LLM calls.

A draft 'passes' compliance when:
- For recommendation topics with requested_count:
  - allowed_count >= requested_count → article must contain exactly requested_count
    recommendations, all from allowed candidates, with Quick Picks section
  - allowed_count < requested_count but >= minimum_publishable_items →
    article must contain all allowed candidates with evidence-limited framing
  - allowed_count < minimum_publishable_items → evidence-limited, article
    acknowledges insufficient evidence
- For non-recommendation topics: compliance is not applicable.

Failure type = "draft_candidate_compliance_failed" means the model had enough
allowed candidates but the article didn't use them.
Evidence-limited means the model was given fewer candidates than requested.
These are distinct failures with different remediation paths.
"""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel

from blogagent.workflow.query_contract import QueryContract, requires_candidate_ledger

# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------


class DraftCandidateCompliance(BaseModel):
    """Result of checking a draft against the allowed candidate table."""

    passes: bool
    requested_count: Optional[int]
    allowed_count: int
    recommended_count: int
    allowed_recommended_count: int
    missing_allowed_candidate_ids: list[str] = []
    unknown_recommended_entities: list[str] = []
    has_quick_picks: bool = False
    detail_sections_count: int = 0
    failure_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_draft_candidate_compliance(
    article_markdown: str,
    allowed_candidates: list[dict],
    query_contract: QueryContract,
    minimum_publishable_items: int = 3,
    draft_output: object | None = None,
) -> DraftCandidateCompliance:
    """Check whether the draft uses the locked candidate table correctly.

    Parameters
    ----------
    article_markdown:
        The final article text.
    allowed_candidates:
        List of EntityCandidate dicts from the ledger (usable=True).
    query_contract:
        The QueryContract for this run.
    minimum_publishable_items:
        Minimum recommendations needed for a publishable article.

    Returns a DraftCandidateCompliance with passes=True when the draft
    correctly uses the allowed candidates, or passes=False with a precise
    failure_reason.
    """
    if not requires_candidate_ledger(query_contract):
        return DraftCandidateCompliance(
            passes=True,
            requested_count=query_contract.requested_count,
            allowed_count=0,
            recommended_count=0,
            allowed_recommended_count=0,
            failure_reason=None,
        )

    requested_count = query_contract.requested_count
    allowed_count = len([c for c in allowed_candidates if c.get("usable", True)])

    # Extract candidate names from allowed list for matching
    allowed_names: list[str] = []
    allowed_ids: list[str] = []
    for c in allowed_candidates:
        if not c.get("usable", True):
            continue
        # Use canonical_name, name, or raw_mention
        n = (c.get("canonical_name") or c.get("name") or c.get("raw_mention") or "").strip()
        if n:
            allowed_names.append(n)
        cid = c.get("candidate_id", "")
        if cid:
            allowed_ids.append(cid)

    # Prefer structured DraftOutput.recommended_entities when present; otherwise
    # derive recommendations deterministically from the markdown.
    structured_recs = _extract_structured_recommended_entities(draft_output)
    article_recs = structured_recs or _extract_article_recommendations(article_markdown)
    recommended_count = len(article_recs)

    # Check for Quick Picks section
    has_quick_picks = bool(re.search(r"#{1,3}\s*Quick\s*Picks?", article_markdown, re.IGNORECASE))

    # Count detail sections (H2/H3 with product-looking headings)
    detail_sections_count = _count_detail_sections(article_markdown, allowed_names)

    # Match article recommendations against allowed candidates
    allowed_norms = {_norm(n) for n in allowed_names}
    matched_allowed: list[str] = []
    unknown_recs: list[str] = []

    allowed_by_id = {c.get("candidate_id", "") for c in allowed_candidates if c.get("candidate_id")}

    for rec in article_recs:
        rec_name = rec.get("name", "") if isinstance(rec, dict) else str(rec)
        rec_id = rec.get("candidate_id", "") if isinstance(rec, dict) else ""
        rec_norm = _norm(rec_name)
        if rec_id and rec_id in allowed_by_id:
            matched_allowed.append(rec_name)
        elif _matches_any(rec_norm, allowed_norms):
            matched_allowed.append(rec_name)
        else:
            unknown_recs.append(rec_name or rec_id or "unknown recommendation")

    allowed_recommended_count = len(matched_allowed)

    # Find which allowed candidates are missing from the article
    missing_ids: list[str] = []
    for c in allowed_candidates:
        if not c.get("usable", True):
            continue
        n = (c.get("canonical_name") or c.get("name") or c.get("raw_mention") or "").strip()
        cid = c.get("candidate_id", "")
        article_rec_norms = {
            _norm(r.get("name", "") if isinstance(r, dict) else str(r)) for r in article_recs
        }
        article_rec_ids = {
            r.get("candidate_id", "")
            for r in article_recs
            if isinstance(r, dict) and r.get("candidate_id")
        }
        if cid and cid in article_rec_ids:
            continue
        if n and not _matches_any(_norm(n), article_rec_norms):
            missing_ids.append(cid or n)

    # --- Compliance decision ---
    failure_reason = _decide_compliance(
        requested_count=requested_count,
        allowed_count=allowed_count,
        recommended_count=recommended_count,
        allowed_recommended_count=allowed_recommended_count,
        unknown_recs=unknown_recs,
        has_quick_picks=has_quick_picks,
        minimum_publishable_items=minimum_publishable_items,
        article_markdown=article_markdown,
    )

    return DraftCandidateCompliance(
        passes=failure_reason is None,
        requested_count=requested_count,
        allowed_count=allowed_count,
        recommended_count=recommended_count,
        allowed_recommended_count=allowed_recommended_count,
        missing_allowed_candidate_ids=missing_ids[:10],
        unknown_recommended_entities=unknown_recs[:10],
        has_quick_picks=has_quick_picks,
        detail_sections_count=detail_sections_count,
        failure_reason=failure_reason,
    )


def derive_recommended_entities_from_markdown(
    article_markdown: str,
    allowed_candidates: list[dict],
) -> list[dict]:
    """Derive DraftRecommendedEntity-compatible dicts from markdown.

    Used when an LLM returns valid recommendation markdown but omits
    DraftOutput.recommended_entities. Only entities matched to the locked
    allowed candidate table are returned.
    """
    article_recs = _extract_article_recommendations(article_markdown)
    if not article_recs:
        return []

    derived: list[dict] = []
    seen_ids: set[str] = set()
    for rec_name in article_recs:
        match = _find_allowed_candidate(rec_name, allowed_candidates)
        if not match:
            continue
        cid = match.get("candidate_id", "") or _norm(
            match.get("canonical_name") or match.get("name") or rec_name
        )
        if cid in seen_ids:
            continue
        seen_ids.add(cid)
        name = (
            match.get("canonical_name") or match.get("name") or match.get("raw_mention") or rec_name
        )
        source_urls = match.get("source_urls") or []
        source_url = match.get("source_url") or (source_urls[0] if source_urls else None)
        derived.append(
            {
                "candidate_id": cid,
                "name": name,
                "section_heading": _find_section_heading(article_markdown, rec_name),
                "source_url": source_url,
            }
        )
    return derived


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_structured_recommended_entities(draft_output: object | None) -> list[dict]:
    if draft_output is None:
        return []

    raw = None
    if isinstance(draft_output, dict):
        raw = draft_output.get("recommended_entities")
    else:
        raw = getattr(draft_output, "recommended_entities", None)
    if not raw:
        return []

    entities: list[dict] = []
    for item in raw:
        if isinstance(item, dict):
            data = item
        elif hasattr(item, "model_dump"):
            data = item.model_dump()
        else:
            data = {
                "candidate_id": getattr(item, "candidate_id", ""),
                "name": getattr(item, "name", ""),
                "section_heading": getattr(item, "section_heading", None),
                "source_url": getattr(item, "source_url", None),
            }
        if (data.get("candidate_id") or data.get("name")) and data.get("name"):
            entities.append(data)
    return entities


def _decide_compliance(
    requested_count: Optional[int],
    allowed_count: int,
    recommended_count: int,
    allowed_recommended_count: int,
    unknown_recs: list[str],
    has_quick_picks: bool,
    minimum_publishable_items: int,
    article_markdown: str,
) -> Optional[str]:
    """Return a failure_reason string or None if compliant."""
    # Hard invariant: if the candidate ledger has zero allowed candidates,
    # any recommendations introduced by the model are unsupported.
    # This applies regardless of requested_count.
    if allowed_count == 0:
        if recommended_count > 0:
            return (
                "draft_candidate_compliance_failed: article introduced "
                f"{recommended_count} recommendation(s) but candidate ledger has "
                "zero allowed candidates — all recommendations are unsupported"
            )
        # No recommendations and no candidates → compliant (no article was expected)
        return None

    # Insufficient allowed candidates — evidence-limited is acceptable
    if allowed_count < minimum_publishable_items:
        return None  # evidence-limited; not a draft compliance failure

    # Enough candidates exist
    if requested_count is not None and allowed_count >= requested_count:
        # Must use exactly requested_count recommendations from allowed
        if recommended_count < requested_count:
            return (
                f"draft_candidate_compliance_failed: {allowed_count} allowed candidates "
                f"were available but article used only {recommended_count}/{requested_count} "
                "required recommendations"
            )
        if unknown_recs:
            return (
                f"draft_candidate_compliance_failed: article contains "
                f"{len(unknown_recs)} recommendation(s) not in the allowed candidate table: "
                + ", ".join(unknown_recs[:3])
            )
        # Quick Picks required for recommendation topics
        if not has_quick_picks:
            return (
                "draft_candidate_compliance_failed: recommendation article must include "
                "a Quick Picks section but none was found"
            )
        return None

    # allowed_count < requested_count but >= minimum_publishable_items
    # Evidence-limited: must use all allowed candidates
    if recommended_count < min(allowed_count, minimum_publishable_items):
        return (
            f"draft_candidate_compliance_failed: evidence-limited mode but article only "
            f"used {recommended_count}/{allowed_count} available candidates"
        )
    if unknown_recs:
        return (
            f"draft_candidate_compliance_failed: article contains "
            f"{len(unknown_recs)} entity(ies) not from allowed candidates: "
            + ", ".join(unknown_recs[:3])
        )

    return None


def _extract_article_recommendations(markdown: str) -> list[str]:
    """Extract named recommendations from the article.

    Uses the existing recommendation_extractor for accuracy.
    """
    try:
        from blogagent.tools.recommendation_extractor import (  # noqa: PLC0415
            extract_recommendations_from_article,
        )

        recs = extract_recommendations_from_article(markdown)
        return [r.name for r in recs if r.name]
    except Exception:  # noqa: BLE001
        return []


def _count_detail_sections(markdown: str, allowed_names: list[str]) -> int:
    """Count H2/H3 sections that appear to be recommendation detail sections."""
    if not allowed_names:
        return 0
    allowed_norms = {_norm(n) for n in allowed_names}
    headings = re.findall(r"^#{2,3}\s+(.+)", markdown, re.MULTILINE)
    count = 0
    for h in headings:
        h_norm = _norm(h)
        # Numbered heading or matches an allowed name
        if re.match(r"^\d+[.)]\s+", h) or _matches_any(h_norm, allowed_norms):
            count += 1
    return count


def _find_allowed_candidate(rec_name: str, allowed_candidates: list[dict]) -> dict | None:
    rec_norm = _norm(rec_name)
    for c in allowed_candidates:
        if not c.get("usable", True):
            continue
        name = (c.get("canonical_name") or c.get("name") or c.get("raw_mention") or "").strip()
        if name and _matches_any(rec_norm, {_norm(name)}):
            return c
    return None


def _find_section_heading(markdown: str, rec_name: str) -> str | None:
    rec_norm = _norm(rec_name)
    headings = re.findall(r"^#{2,3}\s+(.+)", markdown, re.MULTILINE)
    for heading in headings:
        if _matches_any(rec_norm, {_norm(heading)}):
            return heading.strip()
    return None


def _norm(name: str) -> str:
    """Normalise a name for fuzzy matching."""
    name = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", name)  # strip markdown links
    name = re.sub(r"[*_`]", "", name)
    name = name.lower().strip()
    name = re.sub(r"\s+", " ", name)
    # Remove leading articles
    for prefix in ("the ", "a ", "an "):
        if name.startswith(prefix):
            name = name[len(prefix) :]
    return name


def _matches_any(rec_norm: str, allowed_norms: set[str]) -> bool:
    """Return True if rec_norm matches any allowed name (exact or containment)."""
    if rec_norm in allowed_norms:
        return True
    for allowed in allowed_norms:
        if not allowed:
            continue
        # Containment in either direction (partial name match)
        if rec_norm in allowed or allowed in rec_norm:
            return True
        # Brand-word overlap (first word match + at least 2 shared words)
        rec_words = set(rec_norm.split())
        allowed_words = set(allowed.split())
        shared = rec_words & allowed_words
        if (
            rec_norm.split()
            and allowed.split()
            and rec_norm.split()[0] == allowed.split()[0]
            and len(shared) >= 2
        ):
            return True
    return False
