"""claim_extractor tool stub.

Permission class: read_only
Replace the stub implementation with an LLM-backed claim extractor.
"""

from __future__ import annotations

from pydantic import BaseModel

from blogagent.workflow.state import Claim, ClaimImportance


class ClaimExtractInput(BaseModel):
    draft: str
    topic: str


class ClaimExtractOutput(BaseModel):
    claims: list[Claim]
    error: str | None = None


def claim_extractor(input: ClaimExtractInput) -> ClaimExtractOutput:
    """Stub: extracts one placeholder claim. Replace with LLM-backed extractor."""
    claims = [
        Claim(
            text=f"{input.topic} is an important subject.",
            importance=ClaimImportance.medium,
            section="Introduction",
        )
    ]
    return ClaimExtractOutput(claims=claims)
