"""Vercel-compatible FastAPI entry point for BlogAgent.

Exposes a minimal, mock-safe API for serverless deployment.
All routes default to mock mode — no API keys required.

Routes:
    GET  /         → service info
    GET  /health   → service status
    GET  /run      → browser-friendly: no topic → usage hint; topic param → run pipeline
    POST /run      → run the BlogAgent pipeline on a topic (JSON body)

Live provider usage (Tavily search, Anthropic/OpenAI LLM) is optional and cost-bearing.
Configure via Vercel environment variables (see README.md).

Safety:
- Publishing requests are blocked by the pipeline guardrail.
- Raw scraped webpage text is never returned.
- No persistence or external side effects in mock mode.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI(title="BlogAgent API", version="0.1.0")

# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class RunRequest(BaseModel):
    topic: str


class RunResponse(BaseModel):
    blocked: bool
    block_reason: str
    execution_mode: str
    title: str
    meta_description: str
    article_markdown: str
    source_count: int
    claim_status_counts: dict[str, int]
    revision_count: int
    warnings: list[str]
    provider_events: list[str]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "service": "BlogAgent",
        "status": "ok",
        "description": "Source-grounded editorial agent API",
        "endpoints": {
            "health": "GET /health",
            "run_post": "POST /run",
            "run_get": "GET /run?topic=...",
        },
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "BlogAgent", "mode": "mock-safe"}


@app.get("/run")
def run_get(topic: str | None = None) -> Any:
    if not topic or not topic.strip():
        return JSONResponse(
            content={
                "detail": "Use POST /run with JSON body or GET /run?topic=...",
                "example_get": "/run?topic=Why%20elephants%20are%20the%20heaviest%20land%20animals",
                "example_post_body": {
                    "topic": "Why elephants are the heaviest land animals"
                },
            }
        )
    return _run_topic(topic.strip())


@app.post("/run", response_model=RunResponse)
def run(request: RunRequest) -> Any:
    topic = (request.topic or "").strip()
    if not topic:
        raise HTTPException(status_code=400, detail="topic must be a non-empty string")
    return _run_topic(topic)


# ---------------------------------------------------------------------------
# Shared pipeline runner
# ---------------------------------------------------------------------------


def _run_topic(topic: str) -> RunResponse:
    _ensure_mock_safe_defaults()

    from blogagent.workflow.graph import run_pipeline  # noqa: PLC0415

    state = run_pipeline(topic)

    if state.blocked:
        return RunResponse(
            blocked=True,
            block_reason=state.block_reason,
            execution_mode=state.execution_mode,
            title="",
            meta_description="",
            article_markdown="",
            source_count=0,
            claim_status_counts={"supported": 0, "partially_supported": 0, "unsupported": 0},
            revision_count=0,
            warnings=list(state.warnings),
            provider_events=list(state.provider_events),
        )

    pkg = state.final_article_package
    if pkg is None:
        raise HTTPException(status_code=500, detail="Pipeline produced no article package")

    report = pkg.fact_check_report
    return RunResponse(
        blocked=False,
        block_reason="",
        execution_mode=state.execution_mode,
        title=pkg.title,
        meta_description=pkg.meta_description,
        article_markdown=pkg.article_markdown,
        source_count=len(pkg.source_list),
        claim_status_counts={
            "supported": report.supported_count,
            "partially_supported": report.partially_supported_count,
            "unsupported": report.unsupported_count,
        },
        revision_count=state.revision_count,
        warnings=list(state.warnings),
        provider_events=list(state.provider_events),
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _ensure_mock_safe_defaults() -> None:
    """Set mock-safe env defaults if no provider is explicitly configured.

    This keeps the Vercel API safe when env vars are absent.
    Real providers are honoured when the caller has set them via Vercel env vars.
    """
    _setdefault("BLOGAGENT_SEARCH_PROVIDER", "mock")
    _setdefault("BLOGAGENT_LLM_PROVIDER", "mock")
    _setdefault("BLOGAGENT_USE_LLM_EDITOR", "false")
    _setdefault("BLOGAGENT_USE_LLM_FACTCHECK", "false")
    _setdefault("BLOGAGENT_USE_LLM_CITATION_JUDGE", "false")


def _setdefault(key: str, value: str) -> None:
    if not os.environ.get(key):
        os.environ[key] = value
