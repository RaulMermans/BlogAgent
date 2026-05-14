"""LLM client — the single entry point for all structured LLM calls.

Public interface:
    generate_structured(system_prompt, user_prompt, output_model, temperature) -> LLMResult

Provider is selected via BLOGAGENT_LLM_PROVIDER (default: "mock").
If provider is configured but the API key is missing or the package is
not installed, the call falls back to mock with an explicit warning.
Tests run entirely in mock mode and do not require any API key.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from pydantic import BaseModel

from blogagent.llm.providers import (
    AnthropicProvider,
    MissingAPIKeyError,
    OpenAIProvider,
    ProviderResponse,
)
from blogagent.llm.schemas import (
    CitationJudgmentOutput,
    ClaimExtractionOutput,
    ClaimItem,
    DraftOutput,
    FactCheckJudgmentOutput,
    LLMResult,
    OutlineOutput,
    ResearchPlanOutput,
    RevisionOutput,
)

_DEFAULT_TIMEOUT = 60
_MOCK_MODEL = "mock-1.0"
_MOCK_PROVIDER = "mock"

# ---------------------------------------------------------------------------
# Mock data registry — topic-agnostic stand-ins used by the mock provider
# ---------------------------------------------------------------------------

_MOCK_DATA: dict[str, BaseModel] = {
    "ResearchPlanOutput": ResearchPlanOutput(
        research_questions=[
            "What is this topic and why does it matter?",
            "What are the main components or aspects of this subject?",
            "What recent developments have occurred?",
            "What are common misconceptions or debates?",
            "How does this topic affect everyday life or practice?",
        ]
    ),
    "OutlineOutput": OutlineOutput(
        title="Understanding the Topic",
        sections=["Introduction", "Key Facts", "Recent Developments", "Implications", "Conclusion"],
        target_word_count=1000,
        seo_keywords=["topic", "overview", "guide"],
    ),
    "DraftOutput": DraftOutput(
        article_markdown=(
            "# Understanding the Topic\n\n"
            "## Introduction\n\n"
            "This article provides a comprehensive overview of the subject. "
            "Understanding this area is important for researchers, practitioners, and "
            "curious readers alike.\n\n"
            "## Key Facts\n\n"
            "The field encompasses several important dimensions. Evidence from multiple "
            "sources indicates that the topic has both historical roots and contemporary "
            "relevance.\n\n"
            "## Recent Developments\n\n"
            "Significant progress has been made in recent years. New research and "
            "practical applications continue to expand our understanding.\n\n"
            "## Implications\n\n"
            "The broader implications span policy, practice, and public awareness. "
            "Continued study is essential for informed decision-making.\n\n"
            "## Conclusion\n\n"
            "This overview reflects available evidence. Claims requiring further "
            "verification are noted as uncertain."
        ),
        meta_description=(
            "A comprehensive overview of the topic with key facts, "
            "recent developments, and implications."
        ),
        seo_keywords=["topic", "overview", "guide", "facts"],
    ),
    "ClaimExtractionOutput": ClaimExtractionOutput(
        claims=[
            ClaimItem(
                text="This topic has both historical roots and contemporary relevance.",
                importance="medium",
                section="Introduction",
            )
        ]
    ),
    "FactCheckJudgmentOutput": FactCheckJudgmentOutput(
        passed=True,
        revision_required=False,
        blocking_issues=[],
        revision_notes=[],
        confidence="medium",
    ),
    "RevisionOutput": RevisionOutput(
        revised_markdown=(
            "# Understanding the Topic\n\n"
            "## Introduction\n\n"
            "This article provides a comprehensive overview of the subject.\n\n"
            "## Conclusion\n\nThis is a mock revision — no LLM revision was performed."
        ),
        revision_summary=(
            "Mock revision: no LLM provider configured. Draft returned without changes."
        ),
    ),
    "CitationJudgmentOutput": CitationJudgmentOutput(
        claim="(mock claim)",
        support_status="partially_supported",
        confidence="low",
        explanation="Mock citation judgment — no LLM provider configured.",
    ),
}


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


def generate_structured(
    system_prompt: str,
    user_prompt: str,
    output_model: type[BaseModel],
    temperature: float = 0.2,
) -> LLMResult:
    """Call an LLM and parse the response into output_model.

    Falls back to mock if the provider is "mock", the API key is missing,
    the package is not installed, or the call fails for any reason.
    """
    provider_name = os.getenv("BLOGAGENT_LLM_PROVIDER", "mock").strip().lower()

    if provider_name == "mock":
        return _mock_result(output_model)

    try:
        provider = _build_provider(provider_name)
    except (MissingAPIKeyError, ValueError) as exc:
        return _mock_fallback(output_model, warning=str(exc))

    # Augment system prompt with JSON schema so the model knows the output shape.
    schema_str = json.dumps(output_model.model_json_schema(), indent=2)
    augmented_system = (
        f"{system_prompt}\n\n"
        f"Return your response as valid JSON matching this schema:\n{schema_str}\n"
        f"Return only the JSON object. No markdown code fences, no explanation."
    )

    try:
        response: ProviderResponse = provider.generate(augmented_system, user_prompt, temperature)
        parsed = _parse_json_response(response.text, output_model)
        return LLMResult(
            data=parsed,
            provider=provider_name,
            model=response.model,
            is_mock=False,
            raw_text=response.text,
        )
    except ImportError as exc:
        return _mock_fallback(
            output_model,
            warning=f"{provider_name} package not installed: {exc}",
        )
    except Exception as exc:  # noqa: BLE001
        return _mock_fallback(
            output_model,
            error=f"LLM call failed ({type(exc).__name__}: {exc}); using mock fallback.",
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_provider(name: str) -> AnthropicProvider | OpenAIProvider:
    timeout = int(os.getenv("BLOGAGENT_LLM_TIMEOUT_SECONDS", str(_DEFAULT_TIMEOUT)))
    model_override = os.getenv("BLOGAGENT_LLM_MODEL", "").strip()

    if name == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            raise MissingAPIKeyError(
                "ANTHROPIC_API_KEY is not set; falling back to mock LLM output."
            )
        model = model_override or "claude-sonnet-4-6"
        return AnthropicProvider(api_key=api_key, model=model, timeout=timeout)

    if name == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise MissingAPIKeyError(
                "OPENAI_API_KEY is not set; falling back to mock LLM output."
            )
        model = model_override or "gpt-4o-mini"
        return OpenAIProvider(api_key=api_key, model=model, timeout=timeout)

    raise ValueError(
        f"Unknown LLM provider '{name}'. Supported: mock, anthropic, openai."
    )


def _parse_json_response(text: str, output_model: type[BaseModel]) -> Any:
    """Strip optional markdown fences and parse JSON into output_model."""
    cleaned = text.strip()
    # Strip ```json ... ``` or ``` ... ``` blocks
    cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
    cleaned = re.sub(r"\n?```$", "", cleaned.strip())
    data = json.loads(cleaned)
    return output_model.model_validate(data)


def _mock_result(output_model: type[BaseModel]) -> LLMResult:
    data = _MOCK_DATA.get(output_model.__name__)
    return LLMResult(
        data=data,
        provider=_MOCK_PROVIDER,
        model=_MOCK_MODEL,
        is_mock=True,
        warning=(
            None if data is not None
            else f"No mock data registered for {output_model.__name__}"
        ),
    )


def _mock_fallback(
    output_model: type[BaseModel],
    *,
    warning: str | None = None,
    error: str | None = None,
) -> LLMResult:
    data = _MOCK_DATA.get(output_model.__name__)
    return LLMResult(
        data=data,
        provider=_MOCK_PROVIDER,
        model=_MOCK_MODEL,
        is_mock=True,
        warning=warning,
        error=error,
    )
