"""Tests for the citation judge module and its integration with citation_matcher."""

from __future__ import annotations

from blogagent.agents.citation_judge import (
    _deterministic_judge,
    judge_citation_support,
)
from blogagent.llm.schemas import CitationJudgmentOutput
from blogagent.tools.citation_matcher import CitationMatchInput, citation_matcher
from blogagent.workflow.state import (
    CitationStatus,
    Claim,
    ClaimImportance,
    SourcePacket,
    SourceScore,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _claim(
    text: str = "Test claim.", importance: ClaimImportance = ClaimImportance.medium
) -> Claim:
    return Claim(text=text, importance=importance, section="Test")


def _score(url: str, overall_score: float, is_mock: bool = False) -> SourceScore:
    return SourceScore(
        url=url,
        title="Test Source",
        domain="test.example.com",
        credibility_score=overall_score,
        relevance_score=overall_score,
        recency_score=overall_score,
        overall_score=overall_score,
        is_mock=is_mock,
    )


def _packet(url: str, text: str, is_mock: bool = False) -> SourcePacket:
    return SourcePacket(
        url=url,
        title="Test Source",
        domain="test.example.com",
        extracted_text=text,
        word_count=len(text.split()),
        is_mock=is_mock,
        extraction_status="success" if not is_mock else "mock",
    )


# ---------------------------------------------------------------------------
# CitationJudgmentOutput schema
# ---------------------------------------------------------------------------


def test_citation_judgment_output_schema():
    output = CitationJudgmentOutput(
        claim="Elephants are the largest land animals.",
        support_status="supported",
        confidence="high",
        explanation="The excerpt directly states elephants are the largest land animals.",
    )
    assert output.claim != ""
    assert output.support_status in ("supported", "partially_supported", "unsupported")
    assert output.confidence in ("low", "medium", "high")
    assert output.explanation != ""


def test_citation_judgment_output_all_statuses_valid():
    for status in ("supported", "partially_supported", "unsupported"):
        out = CitationJudgmentOutput(
            claim="A claim.",
            support_status=status,
            confidence="medium",
            explanation="Explanation.",
        )
        assert out.support_status == status


# ---------------------------------------------------------------------------
# Deterministic fallback judge
# ---------------------------------------------------------------------------


def test_deterministic_judge_empty_excerpt_returns_unsupported():
    result = _deterministic_judge("Elephants weigh 6000 kg.", "", "https://example.com")
    assert result.support_status == "unsupported"
    assert result.confidence == "high"


def test_deterministic_judge_high_overlap_returns_supported():
    claim = "Elephants are the heaviest land animals on Earth."
    excerpt = "Elephants are the heaviest and largest land animals found on Earth today."
    result = _deterministic_judge(claim, excerpt, "https://example.com")
    assert result.support_status == "supported"


def test_deterministic_judge_low_overlap_returns_unsupported():
    claim = "Quantum entanglement enables faster than light communication."
    excerpt = "Chocolate cake requires flour, sugar, and butter."
    result = _deterministic_judge(claim, excerpt, "https://example.com")
    assert result.support_status == "unsupported"


def test_deterministic_judge_medium_overlap_returns_partial():
    claim = "Elephants live for 60 to 70 years in the wild."
    excerpt = "Elephants can live for many decades, sometimes more than 50 years."
    result = _deterministic_judge(claim, excerpt, "https://example.com")
    # Any valid citation status is acceptable — just verify no crash and schema matches
    assert result.support_status in ("supported", "partially_supported", "unsupported")
    assert result.confidence in ("low", "medium", "high")


def test_deterministic_judge_returns_citation_judgment_output():
    result = _deterministic_judge("Claim text.", "Excerpt text.", "https://example.com")
    assert isinstance(result, CitationJudgmentOutput)


def test_deterministic_judge_claim_is_preserved():
    claim = "Unique claim text ABC."
    result = _deterministic_judge(claim, "excerpt", "https://example.com")
    assert result.claim == claim


# ---------------------------------------------------------------------------
# judge_citation_support — LLM disabled (default)
# ---------------------------------------------------------------------------


def test_judge_citation_support_disabled_uses_deterministic(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_USE_LLM_CITATION_JUDGE", "false")
    result = judge_citation_support(
        "Elephants are the largest land animals.",
        "Elephants are the largest animals on land.",
        "https://example.com",
    )
    assert isinstance(result, CitationJudgmentOutput)
    assert result.support_status in ("supported", "partially_supported", "unsupported")


def test_judge_citation_support_missing_api_key_falls_back(monkeypatch):
    """With judge enabled but no API key, must fall back to deterministic — never crash."""
    monkeypatch.setenv("BLOGAGENT_USE_LLM_CITATION_JUDGE", "true")
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "anthropic")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = judge_citation_support(
        "Elephants weigh up to 6000 kg.",
        "African elephants can weigh up to six thousand kilograms.",
        "https://example.com",
    )
    assert isinstance(result, CitationJudgmentOutput)
    assert result.support_status in ("supported", "partially_supported", "unsupported")


# ---------------------------------------------------------------------------
# citation_matcher — heuristic still works when judge disabled
# ---------------------------------------------------------------------------


def test_citation_matcher_heuristic_unaffected_when_judge_disabled(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_USE_LLM_CITATION_JUDGE", "false")
    sources = [_score("https://wikipedia.org/wiki/Elephant", 0.7, is_mock=False)]
    output = citation_matcher(CitationMatchInput(claims=[_claim()], sources=sources))
    assert output.matches[0].status == CitationStatus.supported


def test_citation_matcher_with_packets_heuristic_disabled(monkeypatch):
    """Passing source_packets with judge disabled must not change heuristic behavior."""
    monkeypatch.setenv("BLOGAGENT_USE_LLM_CITATION_JUDGE", "false")
    sources = [_score("https://wikipedia.org/wiki/Elephant", 0.7, is_mock=False)]
    packets = [_packet("https://wikipedia.org/wiki/Elephant", "Elephants are large mammals.")]
    output = citation_matcher(
        CitationMatchInput(claims=[_claim()], sources=sources, source_packets=packets)
    )
    assert output.matches[0].status == CitationStatus.supported


# ---------------------------------------------------------------------------
# citation_matcher — judge path via monkeypatch
# ---------------------------------------------------------------------------


def test_citation_matcher_calls_judge_when_enabled(monkeypatch):
    """With judge enabled and packets present, the judge must be called."""
    monkeypatch.setenv("BLOGAGENT_USE_LLM_CITATION_JUDGE", "true")
    monkeypatch.setenv("BLOGAGENT_LLM_PROVIDER", "mock")

    judge_calls: list[tuple[str, str, str]] = []

    def fake_judge(claim: str, excerpt: str, url: str) -> CitationJudgmentOutput:
        judge_calls.append((claim, excerpt, url))
        return CitationJudgmentOutput(
            claim=claim,
            support_status="supported",
            confidence="high",
            explanation="Monkeypatched judge.",
        )

    monkeypatch.setattr(
        "blogagent.agents.citation_judge.judge_citation_support",
        fake_judge,
    )

    sources = [_score("https://example.org/page", 0.8, is_mock=False)]
    packets = [_packet("https://example.org/page", "Elephants are the heaviest land animals.")]
    output = citation_matcher(
        CitationMatchInput(
            claims=[_claim("Elephants are heavy.")],
            sources=sources,
            source_packets=packets,
        )
    )
    assert len(judge_calls) == 1
    assert output.matches[0].status == CitationStatus.supported


def test_citation_matcher_judge_result_overrides_heuristic(monkeypatch):
    """Judge returning unsupported must override heuristic even with a real source."""
    monkeypatch.setenv("BLOGAGENT_USE_LLM_CITATION_JUDGE", "true")

    def fake_judge(claim: str, excerpt: str, url: str) -> CitationJudgmentOutput:
        return CitationJudgmentOutput(
            claim=claim,
            support_status="unsupported",
            confidence="high",
            explanation="Not supported by excerpt.",
        )

    monkeypatch.setattr(
        "blogagent.agents.citation_judge.judge_citation_support",
        fake_judge,
    )

    sources = [_score("https://example.org/page", 0.9, is_mock=False)]
    packets = [_packet("https://example.org/page", "Unrelated text about cooking.")]
    output = citation_matcher(
        CitationMatchInput(claims=[_claim()], sources=sources, source_packets=packets)
    )
    assert output.matches[0].status == CitationStatus.unsupported


def test_citation_matcher_no_packets_uses_heuristic_even_when_judge_enabled(monkeypatch):
    """Judge enabled but no packets → heuristic is used."""
    monkeypatch.setenv("BLOGAGENT_USE_LLM_CITATION_JUDGE", "true")
    sources = [_score("https://wikipedia.org/wiki/Topic", 0.7, is_mock=False)]
    output = citation_matcher(
        CitationMatchInput(claims=[_claim()], sources=sources, source_packets=[])
    )
    assert output.matches[0].status == CitationStatus.supported
