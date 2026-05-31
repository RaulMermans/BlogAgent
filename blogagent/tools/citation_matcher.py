"""citation_matcher tool — deterministic heuristic with optional LLM semantic verification.

Permission class: read_only

Classifies each claim based on the quality of available sources.

Default mode (BLOGAGENT_USE_LLM_CITATION_JUDGE=false):
  Applies the same heuristic status to all claims based on the overall source pool:
  - No sources at all                       → unsupported
  - All sources are mock                    → partially_supported
  - All sources have overall_score <= 0     → unsupported (failed sources cannot support claims)
  - At least one non-mock, positive-score source → supported

Optional LLM mode (BLOGAGENT_USE_LLM_CITATION_JUDGE=true):
  When source_packets are provided and a non-empty excerpt is available,
  calls citation_judge.judge_citation_support() per claim for semantic verification.
  Falls back to heuristic if the judge fails or no excerpt is available.
"""

from __future__ import annotations

import os

from pydantic import BaseModel

from blogagent.workflow.state import CitationMatch, CitationStatus, Claim, SourcePacket, SourceScore


class CitationMatchInput(BaseModel):
    claims: list[Claim]
    sources: list[SourceScore]
    source_packets: list[SourcePacket] = []


class CitationMatchOutput(BaseModel):
    matches: list[CitationMatch]
    error: str | None = None


def citation_matcher(input: CitationMatchInput) -> CitationMatchOutput:
    """Match claims to sources.

    Uses heuristic by default. When BLOGAGENT_USE_LLM_CITATION_JUDGE=true and
    source_packets are provided, calls the citation judge per claim.
    """
    use_llm_judge = os.getenv("BLOGAGENT_USE_LLM_CITATION_JUDGE", "false").strip().lower() == "true"

    heuristic_status, heuristic_notes, supporting = _evaluate_sources(input.sources)

    if use_llm_judge and input.source_packets:
        matches = _judge_per_claim(input.claims, input.source_packets, heuristic_status, supporting)
    else:
        matches = [
            CitationMatch(
                claim=claim,
                status=heuristic_status,
                supporting_sources=supporting,
                notes=heuristic_notes,
            )
            for claim in input.claims
        ]

    return CitationMatchOutput(matches=matches)


def _judge_per_claim(
    claims: list[Claim],
    source_packets: list[SourcePacket],
    heuristic_status: CitationStatus,
    heuristic_supporting: list[str],
) -> list[CitationMatch]:
    from blogagent.agents.citation_judge import judge_citation_support  # noqa: PLC0415

    combined_excerpt = _build_combined_excerpt(source_packets)
    primary_url = source_packets[0].url if source_packets else ""

    matches: list[CitationMatch] = []
    for claim in claims:
        if combined_excerpt:
            judgment = judge_citation_support(claim.text, combined_excerpt, primary_url)
            status = CitationStatus(judgment.support_status)
            notes = judgment.explanation
            supporting = heuristic_supporting if status != CitationStatus.unsupported else []
        else:
            status = heuristic_status
            notes = "No source excerpt available; heuristic used."
            supporting = heuristic_supporting
        matches.append(
            CitationMatch(
                claim=claim,
                status=status,
                supporting_sources=supporting,
                notes=notes,
            )
        )
    return matches


def _build_combined_excerpt(source_packets: list[SourcePacket]) -> str:
    """Concatenate extracted text from non-mock real sources, bounded for prompt safety."""
    parts: list[str] = []
    for packet in source_packets:
        if packet.extracted_text and not packet.is_mock:
            parts.append(packet.extracted_text[:500])
    return "\n\n".join(parts)[:2000]


def _evaluate_sources(
    sources: list[SourceScore],
) -> tuple[CitationStatus, str, list[str]]:
    """Return (status, notes, supporting_urls) based on available source quality."""
    if not sources:
        return (
            CitationStatus.unsupported,
            "No sources available — cannot verify claim.",
            [],
        )

    viable = [s for s in sources if s.overall_score > 0]
    if not viable:
        excluded = ", ".join(s.url for s in sources)
        return (
            CitationStatus.unsupported,
            f"All sources have zero score and cannot support claims. Excluded: {excluded}",
            [],
        )

    real = [s for s in viable if not s.is_mock]
    if not real:
        mock_urls = [s.url for s in viable]
        return (
            CitationStatus.partially_supported,
            "Only mock/placeholder sources available — treating as partially supported. "
            "Replace mock sources with real research before finalising.",
            mock_urls[:1],
        )

    return (
        CitationStatus.supported,
        f"Supported by {len(real)} real source(s) with positive score: "
        + ", ".join(s.url for s in real[:3]),
        [s.url for s in real[:3]],
    )
