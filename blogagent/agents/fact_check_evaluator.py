"""Fact-Check Evaluator stub.

Handles claim extraction and citation evaluation.
Replace each stub function with a real LLM call when an API is connected.
"""

from __future__ import annotations

from blogagent.workflow.state import (
    BlogRunState,
    CitationMatch,
    CitationStatus,
    Claim,
    ClaimImportance,
)


def extract_claims(draft: str, topic: str) -> list[Claim]:
    """Stub: extracts one placeholder claim. Replace with LLM call."""
    return [
        Claim(
            text=f"{topic} is an important subject.",
            importance=ClaimImportance.medium,
            section="Introduction",
        )
    ]


def evaluate_citations(claims: list[Claim], state: BlogRunState) -> list[CitationMatch]:
    """Stub: marks all claims as supported. Replace with LLM call."""
    return [
        CitationMatch(
            claim=claim,
            status=CitationStatus.supported,
            supporting_sources=[s.url for s in state.source_scores[:1]],
            notes="Stub match",
        )
        for claim in claims
    ]
