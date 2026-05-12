"""citation_matcher tool stub.

Permission class: read_only
Replace the stub implementation with an LLM-backed citation matcher.
"""

from __future__ import annotations

from pydantic import BaseModel

from blogagent.workflow.state import Claim, CitationMatch, CitationStatus, SourceScore


class CitationMatchInput(BaseModel):
    claims: list[Claim]
    sources: list[SourceScore]


class CitationMatchOutput(BaseModel):
    matches: list[CitationMatch]
    error: str | None = None


def citation_matcher(input: CitationMatchInput) -> CitationMatchOutput:
    """Stub: marks all claims as supported. Replace with LLM-backed matcher."""
    matches = [
        CitationMatch(
            claim=claim,
            status=CitationStatus.supported,
            supporting_sources=[s.url for s in input.sources[:1]],
            notes="Stub match — replace with real citation matching.",
        )
        for claim in input.claims
    ]
    return CitationMatchOutput(matches=matches)
