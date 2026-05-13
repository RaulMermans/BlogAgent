"""citation_matcher tool — deterministic heuristic stub.

Permission class: read_only

Classifies each claim based on the quality of available sources without using an LLM.

Rules (applied per claim):
  - No sources at all                       → unsupported
  - All sources are mock                    → partially_supported
  - All sources have overall_score <= 0     → unsupported (failed sources cannot support claims)
  - At least one non-mock, positive-score source → supported

Replace with an LLM-backed semantic matcher when an API is connected.
"""

from __future__ import annotations

from pydantic import BaseModel

from blogagent.workflow.state import CitationMatch, CitationStatus, Claim, SourceScore


class CitationMatchInput(BaseModel):
    claims: list[Claim]
    sources: list[SourceScore]


class CitationMatchOutput(BaseModel):
    matches: list[CitationMatch]
    error: str | None = None


def citation_matcher(input: CitationMatchInput) -> CitationMatchOutput:
    """Deterministic heuristic citation matching. Replace with LLM-backed matcher when ready."""
    status, notes, supporting = _evaluate_sources(input.sources)
    matches = [
        CitationMatch(
            claim=claim,
            status=status,
            supporting_sources=supporting,
            notes=notes,
        )
        for claim in input.claims
    ]
    return CitationMatchOutput(matches=matches)


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
