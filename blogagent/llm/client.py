"""LLM client — the single entry point for all structured LLM calls.

Public interface:
    generate_structured(system_prompt, user_prompt, output_model, temperature) -> LLMResult
    parse_json_object(text) -> dict
    detect_repeated_excerpts(text, threshold) -> list[str]
    clean_article_markdown(text) -> str

Provider is selected via BLOGAGENT_LLM_PROVIDER (default: "mock").
If provider is configured but the API key is missing or the package is
not installed, the call falls back to mock with an explicit warning.
Tests run entirely in mock mode and do not require any API key.

Every returned LLMResult includes:
    configured_provider — what BLOGAGENT_LLM_PROVIDER requested
    provider            — what actually produced the output
    is_mock             — True when output came from mock data registry
    warning             — set when a configured live provider fell back to mock,
                          "structured_output_repaired=true" after a repair, or
                          "structured_output_completed_missing_fields=true" when
                          missing DraftOutput metadata was synthesised from the article
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from pydantic import BaseModel

from blogagent.llm.providers import (
    AnthropicProvider,
    GoogleProvider,
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
from blogagent.observability.agentpulse_client import current_client, current_node_id

_DEFAULT_TIMEOUT = 60
_MOCK_MODEL = "mock-1.0"
_MOCK_PROVIDER = "mock"

# ---------------------------------------------------------------------------
# Article markdown fence cleaner
# ---------------------------------------------------------------------------


def clean_article_markdown(text: str) -> str:
    """Strip outer markdown code fences from article_markdown.

    Handles the case where an LLM wraps the entire article in:
        ```markdown
        # Title
        ...
        ```
    or plain ``` fences.

    Only strips the outermost fence pair when:
    - The string starts with ```markdown or ```
    - The string ends with ``` (after the newline)
    - The inner content starts with a # heading

    Internal code fences (within the article body) are preserved.
    """
    if not text:
        return text
    stripped = text.strip()

    for prefix in ("```markdown\n", "```markdown\r\n", "```\n", "```\r\n"):
        if stripped.startswith(prefix):
            inner = stripped[len(prefix):]
            # Strip trailing fence
            if inner.endswith("\n```"):
                inner = inner[:-4]
            elif inner.endswith("```"):
                inner = inner[:-3]
            inner = inner.strip()
            # Only accept if content looks like a markdown article
            if inner.startswith("#") or "\n#" in inner:
                return inner
            # Accept any non-empty stripped content when clearly wrapped
            if inner.strip():
                return inner

    return text


# ---------------------------------------------------------------------------
# JSON parsing utilities
# ---------------------------------------------------------------------------


def parse_json_object(text: str) -> dict:
    """Parse a JSON object from text using multiple fallback strategies.

    Strategies (in order):
    1. Strict json.loads on the raw text.
    2. Strip markdown code fences (```json ... ```) then json.loads.
    3. Extract the substring between the first ``{`` and last ``}`` and json.loads.

    Raises json.JSONDecodeError if all strategies fail.
    """
    stripped = text.strip()

    # Strategy 1: direct parse
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    # Strategy 2: strip markdown code fences
    cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", stripped)
    cleaned = re.sub(r"\n?```$", "", cleaned.strip()).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Strategy 3: extract between first { and last }
    first = stripped.find("{")
    last = stripped.rfind("}")
    if first >= 0 and last > first:
        try:
            return json.loads(stripped[first : last + 1])
        except json.JSONDecodeError:
            pass

    raise json.JSONDecodeError("No valid JSON object found in text", stripped, 0)


# ---------------------------------------------------------------------------
# Repeated-text guardrail
# ---------------------------------------------------------------------------


def detect_repeated_excerpts(
    article_markdown: str,
    min_phrase_length: int = 60,
    threshold: int = 3,
) -> list[str]:
    """Return warning strings for any phrase repeated in threshold or more sections.

    Splits the article at ## headings and looks for sentences of at least
    min_phrase_length characters that appear in threshold or more sections.
    """
    sections = re.split(r"\n(?=##\s)", article_markdown)
    if len(sections) < threshold:
        return []

    phrase_section_count: dict[str, int] = {}
    for section_text in sections:
        # Extract sentences (split on sentence-ending punctuation)
        sentences = re.split(r"(?<=[.!?])\s+", section_text)
        seen_in_section: set[str] = set()
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < min_phrase_length:
                continue
            normalized = re.sub(r"\s+", " ", sentence.lower())
            if normalized not in seen_in_section:
                seen_in_section.add(normalized)
                phrase_section_count[normalized] = phrase_section_count.get(normalized, 0) + 1

    warnings: list[str] = []
    for phrase, count in phrase_section_count.items():
        if count >= threshold:
            preview = phrase[:80] + ("..." if len(phrase) > 80 else "")
            warnings.append(f'Repeated excerpt detected in {count} sections: "{preview}"')
    return warnings


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

    Every returned LLMResult has configured_provider set to the value of
    BLOGAGENT_LLM_PROVIDER so callers can distinguish configured vs actual.
    """
    provider_name = os.getenv("BLOGAGENT_LLM_PROVIDER", "mock").strip().lower()
    telemetry = current_client()
    node_id = current_node_id()
    t0 = time.monotonic()
    if telemetry:
        telemetry.model_call_started(
            node_id,
            {
                "model_provider": provider_name,
                "model_name": os.getenv("BLOGAGENT_LLM_MODEL", "").strip() or None,
                "agent": node_id or "unknown",
                "output_schema": output_model.__name__,
                "input_summary": (
                    f"system={len(system_prompt)} chars; user={len(user_prompt)} chars"
                ),
            },
        )

    if provider_name == "mock":
        return _record_model_result(
            _mock_result(output_model, configured_provider="mock"),
            start=t0,
            output_model=output_model,
            node_id=node_id,
        )

    try:
        provider = _build_provider(provider_name)
    except (MissingAPIKeyError, ValueError) as exc:
        return _record_model_result(
            _mock_fallback(output_model, configured_provider=provider_name, warning=str(exc)),
            start=t0,
            output_model=output_model,
            node_id=node_id,
        )

    # Augment system prompt with JSON schema so the model knows the output shape.
    schema_str = json.dumps(output_model.model_json_schema(), indent=2)
    augmented_system = (
        f"{system_prompt}\n\n"
        f"Return your response as valid JSON matching this schema:\n{schema_str}\n"
        f"Return only the JSON object. No markdown code fences, no explanation."
    )

    # --- Provider call ---
    try:
        response: ProviderResponse = provider.generate(augmented_system, user_prompt, temperature)
    except ImportError as exc:
        return _record_model_result(
            _mock_fallback(
                output_model,
                configured_provider=provider_name,
                warning=f"{provider_name} package not installed: {exc}",
            ),
            start=t0,
            output_model=output_model,
            node_id=node_id,
        )
    except Exception as exc:  # noqa: BLE001
        return _record_model_result(
            _mock_fallback(
                output_model,
                configured_provider=provider_name,
                error=f"LLM call failed ({type(exc).__name__}: {exc}); using mock fallback.",
            ),
            start=t0,
            output_model=output_model,
            node_id=node_id,
        )

    # --- JSON parse ---
    try:
        parsed = _parse_json_response(response.text, output_model)
        # Strip outer markdown fences from article_markdown if present.
        if output_model.__name__ == "DraftOutput" and parsed is not None:
            cleaned = clean_article_markdown(parsed.article_markdown)
            if cleaned != parsed.article_markdown:
                parsed = type(parsed)(
                    article_markdown=cleaned,
                    meta_description=parsed.meta_description,
                    seo_keywords=parsed.seo_keywords,
                    recommended_entities=getattr(parsed, "recommended_entities", []),
                )
        return _record_model_result(
            LLMResult(
                data=parsed,
                provider=provider_name,
                model=response.model,
                is_mock=False,
                configured_provider=provider_name,
                raw_text=response.text,
            ),
            start=t0,
            output_model=output_model,
            node_id=node_id,
        )
    except Exception as parse_exc:  # noqa: BLE001
        # For RevisionOutput: try deterministic completion when revised_markdown exists
        # but revision_summary is missing.
        if output_model.__name__ == "RevisionOutput":
            completed, ok = _try_complete_revision_output(response.text, output_model)
            if ok:
                return _record_model_result(
                    LLMResult(
                        data=completed,
                        provider=provider_name,
                        model=response.model,
                        is_mock=False,
                        configured_provider=provider_name,
                        raw_text=response.text,
                        warning="structured_output_completed_missing_fields=true",
                    ),
                    start=t0,
                    output_model=output_model,
                    node_id=node_id,
                )

        # For DraftOutput: try deterministic field completion before repair/mock.
        # This handles the common case where the model returned valid article_markdown
        # but omitted meta_description (a required field).
        if output_model.__name__ == "DraftOutput":
            completed, ok = _try_complete_draft_output(response.text, output_model)
            if ok:
                return _record_model_result(
                    LLMResult(
                        data=completed,
                        provider=provider_name,
                        model=response.model,
                        is_mock=False,
                        configured_provider=provider_name,
                        raw_text=response.text,
                        warning="structured_output_completed_missing_fields=true",
                    ),
                    start=t0,
                    output_model=output_model,
                    node_id=node_id,
                )

        # One repair retry before falling back to mock.
        repaired, ok = _try_repair(provider, response.text, output_model, temperature)
        if ok:
            return _record_model_result(
                LLMResult(
                    data=repaired,
                    provider=provider_name,
                    model=response.model,
                    is_mock=False,
                    configured_provider=provider_name,
                    raw_text=response.text,
                    warning="structured_output_repaired=true",
                ),
                start=t0,
                output_model=output_model,
                node_id=node_id,
            )
        return _record_model_result(
            _mock_fallback(
                output_model,
                configured_provider=provider_name,
                error=(
                    f"JSON parse failed ({type(parse_exc).__name__}: {parse_exc}); "
                    "repair also failed; using mock fallback."
                ),
            ),
            start=t0,
            output_model=output_model,
            node_id=node_id,
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_provider(
    name: str,
) -> AnthropicProvider | OpenAIProvider | GoogleProvider:
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
            raise MissingAPIKeyError("OPENAI_API_KEY is not set; falling back to mock LLM output.")
        model = model_override or "gpt-4o-mini"
        return OpenAIProvider(api_key=api_key, model=model, timeout=timeout)

    if name == "google":
        api_key = os.getenv("GOOGLE_API_KEY", "").strip()
        if not api_key:
            raise MissingAPIKeyError("GOOGLE_API_KEY is not set; falling back to mock LLM output.")
        # Model priority: BLOGAGENT_LLM_MODEL > BLOGAGENT_GOOGLE_MODEL > default
        model = (
            model_override or os.getenv("BLOGAGENT_GOOGLE_MODEL", "").strip() or "gemini-2.5-flash"
        )
        return GoogleProvider(api_key=api_key, model=model, timeout=timeout)

    raise ValueError(f"Unknown LLM provider '{name}'. Supported: mock, anthropic, openai, google.")


def _record_model_result(
    result: LLMResult,
    *,
    start: float,
    output_model: type[BaseModel],
    node_id: str | None,
) -> LLMResult:
    telemetry = current_client()
    if telemetry is None:
        return result

    metadata = {
        "model_provider": result.provider,
        "model_name": result.model,
        "configured_provider": result.configured_provider,
        "agent": node_id or "unknown",
        "output_schema": output_model.__name__,
        "is_mock": result.is_mock,
        "fallback": result.is_mock and result.configured_provider != "mock",
        "input_tokens": None,
        "output_tokens": None,
        "cost_usd": None,
        "latency_ms": int((time.monotonic() - start) * 1000),
        "warning": result.warning,
        "error": result.error,
    }
    if result.error:
        telemetry.model_call_failed(node_id, metadata)
    else:
        telemetry.model_call_completed(node_id, metadata)
    return result


def _parse_json_response(text: str, output_model: type[BaseModel]) -> Any:
    """Parse JSON from provider text into output_model via parse_json_object."""
    data = parse_json_object(text)
    return output_model.model_validate(data)


def _try_repair(
    provider: AnthropicProvider | OpenAIProvider | GoogleProvider,
    text: str,
    output_model: type[BaseModel],
    temperature: float,
) -> tuple[Any, bool]:
    """Attempt one repair call to fix malformed JSON output.

    Sends the raw bad text back to the same provider with a strict repair
    instruction.  Returns (parsed_data, True) on success or (None, False).
    """
    repair_system = (
        "You are a JSON repair assistant. Return only valid JSON with no commentary or explanation."
    )

    # Schema-specific instructions for DraftOutput to avoid common failures
    if output_model.__name__ == "DraftOutput":
        schema_hint = (
            "\n\nFor a DraftOutput the required fields are:\n"
            '  "article_markdown": the full article as markdown text (string)\n'
            '  "meta_description": 120-160 character summary (string, required)\n'
            '  "seo_keywords": list of 3-6 keywords (array of strings, may be empty)\n\n'
            "Rules:\n"
            "- Do NOT wrap article_markdown in ```markdown or ``` fences.\n"
            "- Preserve article_markdown exactly unless it is malformed.\n"
            "- If meta_description is missing, write a 1-2 sentence description from the article.\n"
            "- Output valid JSON only, no code fences around the JSON."
        )
    else:
        schema_hint = ""

    repair_user = (
        "Convert the following malformed model output into valid JSON only. "
        "Preserve all fields and content. Do not add commentary."
        + schema_hint
        + "\n\n"
        + text
    )
    try:
        response = provider.generate(repair_system, repair_user, temperature=0.0)
        data = parse_json_object(response.text)
        parsed = output_model.model_validate(data)
        # Clean fences in repaired DraftOutput too
        if output_model.__name__ == "DraftOutput":
            cleaned = clean_article_markdown(parsed.article_markdown)
            if cleaned != parsed.article_markdown:
                parsed = type(parsed)(
                    article_markdown=cleaned,
                    meta_description=parsed.meta_description,
                    seo_keywords=parsed.seo_keywords,
                    recommended_entities=getattr(parsed, "recommended_entities", []),
                )
        return parsed, True
    except Exception:  # noqa: BLE001
        return None, False


def _try_complete_draft_output(
    raw_text: str,
    output_model: type[BaseModel],
) -> tuple[Any, bool]:
    """Attempt to complete missing required fields for DraftOutput.

    Called when JSON parsed but model validation failed (e.g., meta_description missing).
    Synthesises missing title/meta_description/seo_keywords from the article_markdown.

    Returns (parsed_instance, True) on success or (None, False).
    Only applies when output_model is DraftOutput and article_markdown is present.
    """
    if output_model.__name__ != "DraftOutput":
        return None, False

    try:
        data = parse_json_object(raw_text)
    except Exception:
        return None, False

    markdown = data.get("article_markdown", "")
    if not markdown or not markdown.strip():
        return None, False

    # Strip outer fences first
    markdown = clean_article_markdown(markdown)
    data["article_markdown"] = markdown

    # Synthesise meta_description from first prose paragraph
    if not data.get("meta_description", "").strip():
        desc = _synthesise_meta_description(markdown)
        if desc:
            data["meta_description"] = desc

    # Synthesise seo_keywords from headings
    if not data.get("seo_keywords"):
        data["seo_keywords"] = _synthesise_seo_keywords(markdown)

    try:
        return output_model.model_validate(data), True
    except Exception:
        return None, False


def _try_complete_revision_output(
    raw_text: str,
    output_model: type[BaseModel],
) -> tuple[Any, bool]:
    """Attempt to complete missing fields for RevisionOutput.

    Called when JSON parsed but validation failed (e.g., revision_summary missing).
    If revised_markdown is present, synthesise revision_summary from it.
    Only falls back to mock if revised_markdown is also missing.

    Returns (parsed_instance, True) on success or (None, False).
    """
    if output_model.__name__ != "RevisionOutput":
        return None, False

    try:
        data = parse_json_object(raw_text)
    except Exception:
        return None, False

    markdown = data.get("revised_markdown", "")
    if not markdown or not markdown.strip():
        # revised_markdown missing — cannot complete, must fallback to mock
        return None, False

    # Synthesise summary if missing
    if not data.get("revision_summary", "").strip():
        data["revision_summary"] = (
            "Revision returned revised_markdown without summary; summary synthesized."
        )

    try:
        return output_model.model_validate(data), True
    except Exception:
        return None, False


def _synthesise_meta_description(markdown: str) -> str:
    """Extract the first prose paragraph from markdown as a meta description."""
    for line in markdown.split("\n"):
        line = line.strip()
        if not line:
            continue
        # Skip headings, bullets, numbered items, blockquotes, and code blocks
        if line.startswith(("#", "-", "*", ">", "`", "!", "1.", "2.", "3.")):
            continue
        # Use as description; cap at 160 chars on a word boundary
        if len(line) <= 160:
            return line
        truncated = line[:157].rsplit(" ", 1)[0]
        return truncated + "..."
    return ""


def _synthesise_seo_keywords(markdown: str) -> list[str]:
    """Derive 3–6 keywords from headings in the article markdown."""
    headings = re.findall(r"^#{1,3}\s+(.+)", markdown, re.MULTILINE)
    words: list[str] = []
    seen: set[str] = set()
    # Stop-words to skip
    skip = {
        "the", "a", "an", "and", "or", "but", "for", "to", "in", "of", "is",
        "are", "was", "were", "with", "by", "at", "on", "how", "why", "what",
        "our", "we", "you", "your", "this", "that", "it", "be", "been", "as",
    }
    for heading in headings:
        for word in re.findall(r"\b[a-zA-Z]{4,}\b", heading.lower()):
            if word not in skip and word not in seen:
                seen.add(word)
                words.append(word)
            if len(words) >= 6:
                break
        if len(words) >= 6:
            break
    return words[:6]


def _mock_result(output_model: type[BaseModel], *, configured_provider: str = "mock") -> LLMResult:
    data = _MOCK_DATA.get(output_model.__name__)
    return LLMResult(
        data=data,
        provider=_MOCK_PROVIDER,
        model=_MOCK_MODEL,
        is_mock=True,
        configured_provider=configured_provider,
        warning=(
            None if data is not None else f"No mock data registered for {output_model.__name__}"
        ),
    )


def _mock_fallback(
    output_model: type[BaseModel],
    *,
    configured_provider: str,
    warning: str | None = None,
    error: str | None = None,
) -> LLMResult:
    data = _MOCK_DATA.get(output_model.__name__)
    return LLMResult(
        data=data,
        provider=_MOCK_PROVIDER,
        model=_MOCK_MODEL,
        is_mock=True,
        configured_provider=configured_provider,
        warning=warning,
        error=error,
    )
