"""web_search tool.

Permission class: read_only

Provider selection via BLOGAGENT_SEARCH_PROVIDER env var (default: mock).
Supported: mock, tavily.

If provider is tavily but TAVILY_API_KEY is missing or the call fails,
falls back to mock with an explicit warning field.
"""

from __future__ import annotations

import os
from typing import Optional

from pydantic import BaseModel

from blogagent.workflow.state import SearchResult

_DEFAULT_MAX_RESULTS = 5


class SearchInput(BaseModel):
    query: str
    max_results: int = _DEFAULT_MAX_RESULTS


class SearchOutput(BaseModel):
    results: list[SearchResult]
    query: str
    provider: str = "mock"
    error: Optional[str] = None
    warning: Optional[str] = None


def web_search(input: SearchInput) -> SearchOutput:
    """Search for sources on a topic. Provider is controlled by BLOGAGENT_SEARCH_PROVIDER."""
    max_results = min(
        input.max_results,
        int(os.getenv("BLOGAGENT_MAX_SEARCH_RESULTS", str(_DEFAULT_MAX_RESULTS))),
    )
    capped = SearchInput(query=input.query, max_results=max_results)

    provider = os.getenv("BLOGAGENT_SEARCH_PROVIDER", "mock").strip().lower()
    if provider == "tavily":
        return _tavily_search(capped)
    return _mock_search(capped)


# ---------------------------------------------------------------------------
# Mock provider
# ---------------------------------------------------------------------------


def _mock_search(input: SearchInput) -> SearchOutput:
    slug = input.query.replace(" ", "-").lower()
    results = [
        SearchResult(
            url=f"https://mock-source-{i + 1}.example.dev/{slug}",
            title=f"[MOCK] Source {i + 1}: {input.query}",
            snippet=f"Mock research content about {input.query} from source {i + 1}. "
            f"This is placeholder data for development and testing only.",
            domain=f"mock-source-{i + 1}.example.dev",
            is_mock=True,
        )
        for i in range(input.max_results)
    ]
    return SearchOutput(results=results, query=input.query, provider="mock")


def _mock_fallback(input: SearchInput, warning: str) -> SearchOutput:
    out = _mock_search(input)
    out.warning = warning
    return out


# ---------------------------------------------------------------------------
# Tavily provider
# ---------------------------------------------------------------------------


def _tavily_search(input: SearchInput) -> SearchOutput:
    api_key = os.getenv("TAVILY_API_KEY", "").strip()
    if not api_key:
        return _mock_fallback(
            input,
            "TAVILY_API_KEY is not set; falling back to mock search results.",
        )

    try:
        import httpx  # noqa: PLC0415
    except ImportError:
        return _mock_fallback(
            input,
            "httpx is not installed; falling back to mock search results. Run: uv sync",
        )

    timeout = int(os.getenv("BLOGAGENT_HTTP_TIMEOUT_SECONDS", "15"))
    try:
        resp = httpx.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": input.query,
                "max_results": input.max_results,
                "search_depth": "basic",
                "include_answer": False,
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        results = [
            SearchResult(
                url=item.get("url", ""),
                title=item.get("title", "Untitled"),
                snippet=item.get("content", "")[:500],
                domain=_extract_domain(item.get("url", "")),
                is_mock=False,
            )
            for item in data.get("results", [])[: input.max_results]
            if item.get("url")
        ]
        return SearchOutput(results=results, query=input.query, provider="tavily")
    except Exception as exc:
        return _mock_fallback(
            input,
            f"Tavily search failed ({exc!r}); falling back to mock search results.",
        )


def _extract_domain(url: str) -> str:
    try:
        from urllib.parse import urlparse  # noqa: PLC0415

        return urlparse(url).netloc
    except Exception:
        return ""
