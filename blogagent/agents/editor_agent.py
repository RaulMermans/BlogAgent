"""Editor Agent stub.

Handles research planning, outline generation, drafting, and revision.
Replace each stub function with a real LLM call when an API is connected.
"""

from __future__ import annotations

from blogagent.workflow.state import BlogOutline, BlogRunState


def plan_research(state: BlogRunState) -> list[str]:
    """Stub: returns placeholder research questions. Replace with LLM call."""
    return [
        f"What is {state.topic}?",
        f"What are the key facts about {state.topic}?",
        f"What are the latest developments in {state.topic}?",
    ]


def generate_outline(state: BlogRunState) -> BlogOutline:
    """Stub: returns a placeholder outline. Replace with LLM call."""
    return BlogOutline(
        title=f"Understanding {state.topic}",
        sections=["Introduction", "Key Facts", "Recent Developments", "Conclusion"],
        target_word_count=1000,
        seo_keywords=[state.topic],
    )


def write_draft(state: BlogRunState) -> str:
    """Stub: returns a placeholder draft. Replace with LLM call."""
    assert state.outline is not None, "Outline must exist before drafting"
    sections = "\n\n".join(
        f"## {section}\n\n[Placeholder content for {section}.]"
        for section in state.outline.sections
    )
    return f"# {state.outline.title}\n\n{sections}"


def revise_draft(state: BlogRunState, issues: list[str]) -> str:
    """Stub: returns draft unchanged. Replace with LLM revision call."""
    return state.draft
