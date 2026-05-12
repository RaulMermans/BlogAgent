"""source_score tool stub.

Permission class: read_only
Replace the stub implementation with real credibility, relevance, and recency scoring.
"""

from __future__ import annotations

from pydantic import BaseModel

from blogagent.workflow.state import SourcePacket, SourceScore


class ScoreInput(BaseModel):
    packet: SourcePacket
    topic: str


def source_score(input: ScoreInput) -> SourceScore:
    """Stub: returns uniform placeholder scores. Replace with real scoring logic."""
    return SourceScore(
        url=input.packet.url,
        title=input.packet.title,
        domain=input.packet.domain,
        credibility_score=0.7,
        relevance_score=0.7,
        recency_score=0.7,
        overall_score=0.7,
        notes="Stub score — replace with real scoring logic.",
    )
