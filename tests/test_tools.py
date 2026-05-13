"""Tests for tool modules: web_search, webpage_extract, source_score, citation_matcher."""

from __future__ import annotations

from pathlib import Path

from blogagent.tools.citation_matcher import CitationMatchInput, citation_matcher
from blogagent.tools.source_score import ScoreInput, source_score
from blogagent.tools.web_search import SearchInput, SearchOutput, web_search
from blogagent.tools.webpage_extract import ExtractInput, ExtractOutput, webpage_extract
from blogagent.workflow.state import (
    CitationStatus,
    Claim,
    ClaimImportance,
    SourcePacket,
    SourceScore,
)

# ---------------------------------------------------------------------------
# CLAUDE.md formatting
# ---------------------------------------------------------------------------


def test_claude_md_no_escaped_heading_markers():
    content = (Path(__file__).parent.parent / "CLAUDE.md").read_text()
    assert "\\#" not in content, "CLAUDE.md must not contain escaped # heading markers"


def test_claude_md_no_escaped_horizontal_rules():
    content = (Path(__file__).parent.parent / "CLAUDE.md").read_text()
    assert "\\---" not in content, "CLAUDE.md must not contain escaped --- horizontal rules"


# ---------------------------------------------------------------------------
# web_search — mock provider
# ---------------------------------------------------------------------------


def test_web_search_mock_returns_search_results():
    output = web_search(SearchInput(query="climate change", max_results=3))
    assert isinstance(output, SearchOutput)
    assert len(output.results) == 3
    assert output.provider == "mock"
    assert output.error is None


def test_web_search_mock_results_are_marked_is_mock():
    output = web_search(SearchInput(query="climate change", max_results=3))
    for result in output.results:
        assert result.is_mock is True, f"Expected is_mock=True for {result.url}"


def test_web_search_mock_results_have_required_fields():
    output = web_search(SearchInput(query="solar energy", max_results=2))
    for result in output.results:
        assert result.url != ""
        assert result.title != ""
        assert result.snippet != ""
        assert result.domain != ""


def test_web_search_mock_respects_max_results():
    output = web_search(SearchInput(query="test", max_results=2))
    assert len(output.results) == 2


def test_web_search_mock_urls_do_not_use_real_domains():
    output = web_search(SearchInput(query="test", max_results=3))
    for result in output.results:
        assert "example.dev" in result.url or "mock" in result.url, (
            f"Mock search result URL should use example.dev domain, got: {result.url}"
        )


# ---------------------------------------------------------------------------
# web_search — Tavily provider without API key
# ---------------------------------------------------------------------------


def test_web_search_tavily_without_api_key_falls_back_to_mock(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_SEARCH_PROVIDER", "tavily")
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    output = web_search(SearchInput(query="test", max_results=2))
    assert output.provider == "mock"
    assert output.warning is not None
    assert "TAVILY_API_KEY" in output.warning


def test_web_search_tavily_fallback_results_are_mock(monkeypatch):
    monkeypatch.setenv("BLOGAGENT_SEARCH_PROVIDER", "tavily")
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    output = web_search(SearchInput(query="test", max_results=2))
    for result in output.results:
        assert result.is_mock is True


# ---------------------------------------------------------------------------
# webpage_extract — mock URLs
# ---------------------------------------------------------------------------


def test_webpage_extract_mock_url_returns_source_packet():
    output = webpage_extract(
        ExtractInput(
            url="https://mock-source-1.example.dev/test",
            title="Test Source",
            domain="mock-source-1.example.dev",
        )
    )
    assert isinstance(output, ExtractOutput)
    assert output.packet is not None
    assert output.error is None


def test_webpage_extract_mock_url_is_marked_mock():
    output = webpage_extract(
        ExtractInput(
            url="https://mock-source-1.example.dev/test",
            title="Test Source",
            domain="mock-source-1.example.dev",
        )
    )
    assert output.packet is not None
    assert output.packet.is_mock is True
    assert output.packet.extraction_status == "mock"


def test_webpage_extract_mock_url_has_non_empty_text():
    output = webpage_extract(
        ExtractInput(
            url="https://mock-source-1.example.dev/test",
            title="Test Source",
            domain="mock-source-1.example.dev",
        )
    )
    assert output.packet is not None
    assert output.packet.extracted_text != ""


def test_webpage_extract_example_com_treated_as_mock():
    output = webpage_extract(
        ExtractInput(
            url="https://example.com/some-page",
            title="Example Page",
            domain="example.com",
        )
    )
    assert output.packet is not None
    assert output.packet.is_mock is True


# ---------------------------------------------------------------------------
# webpage_extract — real URL failure handling
# ---------------------------------------------------------------------------


def test_webpage_extract_failed_url_returns_error_packet():
    """A non-existent host (.invalid TLD) must fail fast without raising."""
    output = webpage_extract(
        ExtractInput(
            url="https://this-host-does-not-exist-12345.invalid/page",
            title="Bad URL",
            domain="this-host-does-not-exist-12345.invalid",
        )
    )
    assert output.packet is not None, "Should return an error packet, not None"
    assert output.packet.extraction_status == "failed"
    assert output.error is not None
    assert output.packet.error_message is not None


def test_webpage_extract_failed_url_packet_has_correct_fields():
    output = webpage_extract(
        ExtractInput(
            url="https://this-host-does-not-exist-12345.invalid/page",
            title="Bad URL",
            domain="this-host-does-not-exist-12345.invalid",
        )
    )
    assert output.packet is not None
    assert output.packet.is_mock is False
    assert output.packet.extracted_text == ""
    assert output.packet.word_count == 0


# ---------------------------------------------------------------------------
# source_score
# ---------------------------------------------------------------------------


def _mock_packet(i: int = 1) -> SourcePacket:
    return SourcePacket(
        url=f"https://mock-source-{i}.example.dev/test",
        title=f"Mock Source {i}",
        domain=f"mock-source-{i}.example.dev",
        extracted_text="Mock content for testing.",
        word_count=4,
        is_mock=True,
        extraction_status="mock",
    )


def _real_packet() -> SourcePacket:
    return SourcePacket(
        url="https://wikipedia.org/wiki/Climate_change",
        title="Climate change",
        domain="wikipedia.org",
        extracted_text=(
            "Climate change is the long-term shift in global temperatures and weather patterns. "
            "It has been driven primarily by human activities since the 1800s. "
            "Rising greenhouse gas emissions have caused global temperatures to increase."
        ),
        word_count=40,
        is_mock=False,
        extraction_status="success",
    )


def test_source_score_mock_packet_is_marked_mock():
    score = source_score(ScoreInput(packet=_mock_packet(), topic="climate change"))
    assert score.is_mock is True


def test_source_score_mock_packet_has_low_overall_score():
    score = source_score(ScoreInput(packet=_mock_packet(), topic="climate change"))
    assert score.overall_score <= 0.5


def test_source_score_real_trusted_domain_has_high_credibility():
    score = source_score(ScoreInput(packet=_real_packet(), topic="climate change"))
    assert score.credibility_score >= 0.8


def test_source_score_real_packet_not_marked_mock():
    score = source_score(ScoreInput(packet=_real_packet(), topic="climate change"))
    assert score.is_mock is False


def test_source_score_relevance_improves_with_keyword_overlap():
    packet_relevant = SourcePacket(
        url="https://example.org/a",
        title="Climate Science",
        domain="example.org",
        extracted_text="Climate change affects temperature and weather patterns globally.",
        word_count=10,
        is_mock=False,
        extraction_status="success",
    )
    packet_irrelevant = SourcePacket(
        url="https://example.org/b",
        title="Cookie Recipes",
        domain="example.org",
        extracted_text="Bake at 350 degrees. Add chocolate chips and butter.",
        word_count=10,
        is_mock=False,
        extraction_status="success",
    )
    score_rel = source_score(ScoreInput(packet=packet_relevant, topic="climate change"))
    score_irr = source_score(ScoreInput(packet=packet_irrelevant, topic="climate change"))
    assert score_rel.relevance_score > score_irr.relevance_score


def test_source_score_failed_extraction_returns_zero_scores():
    packet = SourcePacket(
        url="https://bad.host/page",
        title="Bad",
        domain="bad.host",
        extracted_text="",
        word_count=0,
        is_mock=False,
        extraction_status="failed",
        error_message="Connection refused",
    )
    score = source_score(ScoreInput(packet=packet, topic="anything"))
    assert score.overall_score == 0.0
    assert score.credibility_score == 0.0


# ---------------------------------------------------------------------------
# citation_matcher — deterministic heuristic logic
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


def test_citation_matcher_no_sources_marks_unsupported():
    output = citation_matcher(CitationMatchInput(claims=[_claim()], sources=[]))
    assert len(output.matches) == 1
    assert output.matches[0].status == CitationStatus.unsupported


def test_citation_matcher_no_sources_has_no_supporting_urls():
    output = citation_matcher(CitationMatchInput(claims=[_claim()], sources=[]))
    assert output.matches[0].supporting_sources == []


def test_citation_matcher_no_sources_note_mentions_cannot_verify():
    output = citation_matcher(CitationMatchInput(claims=[_claim()], sources=[]))
    assert "cannot verify" in output.matches[0].notes.lower()


def test_citation_matcher_mock_only_sources_marks_partially_supported():
    sources = [_score("https://mock-source-1.example.dev/a", 0.3, is_mock=True)]
    output = citation_matcher(CitationMatchInput(claims=[_claim()], sources=sources))
    assert output.matches[0].status == CitationStatus.partially_supported


def test_citation_matcher_mock_only_note_explains_placeholder():
    sources = [_score("https://mock-source-1.example.dev/a", 0.3, is_mock=True)]
    output = citation_matcher(CitationMatchInput(claims=[_claim()], sources=sources))
    assert "mock" in output.matches[0].notes.lower()


def test_citation_matcher_zero_score_source_marks_unsupported():
    sources = [_score("https://failed.example.com/page", 0.0, is_mock=False)]
    output = citation_matcher(CitationMatchInput(claims=[_claim()], sources=sources))
    assert output.matches[0].status == CitationStatus.unsupported


def test_citation_matcher_zero_score_source_has_no_supporting_urls():
    sources = [_score("https://failed.example.com/page", 0.0, is_mock=False)]
    output = citation_matcher(CitationMatchInput(claims=[_claim()], sources=sources))
    assert output.matches[0].supporting_sources == []


def test_citation_matcher_real_positive_score_marks_supported():
    sources = [_score("https://wikipedia.org/wiki/Topic", 0.7, is_mock=False)]
    output = citation_matcher(CitationMatchInput(claims=[_claim()], sources=sources))
    assert output.matches[0].status == CitationStatus.supported


def test_citation_matcher_real_source_appears_in_supporting_urls():
    url = "https://wikipedia.org/wiki/Topic"
    sources = [_score(url, 0.7, is_mock=False)]
    output = citation_matcher(CitationMatchInput(claims=[_claim()], sources=sources))
    assert url in output.matches[0].supporting_sources


def test_citation_matcher_applies_same_status_to_all_claims():
    claims = [_claim("Claim A."), _claim("Claim B."), _claim("Claim C.")]
    sources = [_score("https://wikipedia.org/wiki/Topic", 0.7, is_mock=False)]
    output = citation_matcher(CitationMatchInput(claims=claims, sources=sources))
    statuses = {m.status for m in output.matches}
    assert len(statuses) == 1, "All claims should receive the same status from heuristic logic"


def test_citation_matcher_mixed_mock_and_real_marks_supported():
    sources = [
        _score("https://mock-source-1.example.dev/a", 0.3, is_mock=True),
        _score("https://wikipedia.org/wiki/Topic", 0.7, is_mock=False),
    ]
    output = citation_matcher(CitationMatchInput(claims=[_claim()], sources=sources))
    assert output.matches[0].status == CitationStatus.supported
