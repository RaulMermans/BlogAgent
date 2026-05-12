"""webpage_extract tool stub.

Permission class: read_only (network read)
Replace the stub implementation with a real HTTP fetch and text extractor.
"""

from __future__ import annotations

from pydantic import BaseModel

from blogagent.workflow.state import SourcePacket


class ExtractInput(BaseModel):
    url: str
    title: str
    domain: str


class ExtractOutput(BaseModel):
    packet: SourcePacket | None = None
    error: str | None = None


def webpage_extract(input: ExtractInput) -> ExtractOutput:
    """Stub: returns placeholder extracted text. Replace with real HTTP fetch + parser."""
    packet = SourcePacket(
        url=input.url,
        title=input.title,
        domain=input.domain,
        extracted_text=f"[Stub: extracted content from {input.url}]",
        word_count=50,
    )
    return ExtractOutput(packet=packet)
