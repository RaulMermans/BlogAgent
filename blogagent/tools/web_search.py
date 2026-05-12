"""web_search tool stub.

Permission class: read_only
Replace the stub implementation with a real search API call.
"""

from __future__ import annotations

from pydantic import BaseModel

from blogagent.workflow.state import SearchResult


class SearchInput(BaseModel):
    query: str
    max_results: int = 5


class SearchOutput(BaseModel):
    results: list[SearchResult]
    query: str
    error: str | None = None


def web_search(input: SearchInput) -> SearchOutput:
    """Stub: returns placeholder search results. Replace with real search API."""
    results = [
        SearchResult(
            url=f"https://example{i}.com/{input.query.replace(' ', '-').lower()}",
            title=f"Source {i + 1} on {input.query}",
            snippet=f"Information about {input.query} from source {i + 1}.",
            domain=f"example{i}.com",
        )
        for i in range(min(input.max_results, 3))
    ]
    return SearchOutput(results=results, query=input.query)
