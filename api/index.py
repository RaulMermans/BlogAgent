"""Vercel-compatible FastAPI entry point for BlogAgent.

Exposes a minimal, mock-safe API for serverless deployment.
All routes default to mock mode — no API keys required.

Routes:
    GET  /         → service info
    GET  /health   → service status
    GET  /app      → browser UI (HTML)
    GET  /run      → browser-friendly: no topic → usage hint; topic param → run pipeline
    POST /run      → run the BlogAgent pipeline on a topic (JSON body)

Worker secret (optional):
    Set BLOGAGENT_WORKER_SECRET to require a secret on /run endpoints.
    Pass via header X-BlogAgent-Secret, JSON body field worker_secret,
    or query param worker_secret (GET /run only).
    /health, /, and /app remain public regardless.

Safety:
- Publishing requests are blocked by the pipeline guardrail.
- Raw scraped webpage text is never returned.
- No persistence or external side effects in mock mode.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

app = FastAPI(title="BlogAgent API", version="0.1.0")

# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class RunRequest(BaseModel):
    topic: str
    worker_secret: str = ""


class RunResponse(BaseModel):
    blocked: bool
    block_reason: str
    execution_mode: str
    title: str
    slug: str
    meta_description: str
    seo_keywords: list[str]
    article_markdown: str
    source_count: int
    claim_status_counts: dict[str, int]
    revision_count: int
    warnings: list[str]
    provider_events: list[str]


# ---------------------------------------------------------------------------
# Worker secret guard
# ---------------------------------------------------------------------------


def _check_worker_secret(request: Request, body_secret: str = "", query_secret: str = "") -> None:
    """Raise 401 if BLOGAGENT_WORKER_SECRET is set and the request doesn't match.

    Checks (in order): X-BlogAgent-Secret header, body field, query param.
    Does nothing when the env var is unset or empty.
    """
    required = os.environ.get("BLOGAGENT_WORKER_SECRET", "").strip()
    if not required:
        return

    header_secret = request.headers.get("X-BlogAgent-Secret", "")
    provided = header_secret or body_secret or query_secret

    if provided != required:
        raise HTTPException(status_code=401, detail="Invalid or missing worker secret")


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
            "app": "GET /app",
            "run_post": "POST /run",
            "run_get": "GET /run?topic=...",
        },
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "BlogAgent", "mode": "mock-safe"}


@app.get("/app", response_class=HTMLResponse)
def app_ui() -> HTMLResponse:
    html = _build_app_html()
    return HTMLResponse(content=html)


@app.get("/run")
def run_get(
    request: Request,
    topic: str | None = None,
    worker_secret: str = "",
) -> Any:
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
    _check_worker_secret(request, query_secret=worker_secret)
    return _run_topic(topic.strip())


@app.post("/run", response_model=RunResponse)
def run(request: Request, body: RunRequest) -> Any:
    topic = (body.topic or "").strip()
    if not topic:
        raise HTTPException(status_code=400, detail="topic must be a non-empty string")
    _check_worker_secret(request, body_secret=body.worker_secret)
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
            slug="",
            meta_description="",
            seo_keywords=[],
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
        slug=pkg.slug,
        meta_description=pkg.meta_description,
        seo_keywords=list(pkg.seo_keywords),
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
# Browser UI HTML
# ---------------------------------------------------------------------------


def _build_app_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>BlogAgent</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: system-ui, -apple-system, sans-serif;
      background: #f5f5f5;
      color: #1a1a1a;
      padding: 2rem 1rem;
      line-height: 1.6;
    }
    .container { max-width: 900px; margin: 0 auto; }
    h1 { font-size: 2rem; font-weight: 700; }
    .subtitle { color: #555; margin-bottom: 2rem; }

    .form-card {
      background: #fff;
      border: 1px solid #e0e0e0;
      border-radius: 8px;
      padding: 1.5rem;
      margin-bottom: 1.5rem;
    }
    label { display: block; font-weight: 600; margin-bottom: 0.3rem; font-size: 0.9rem; }
    input[type="text"], input[type="password"], textarea {
      width: 100%;
      padding: 0.6rem 0.8rem;
      border: 1px solid #ccc;
      border-radius: 6px;
      font-size: 1rem;
      font-family: inherit;
      margin-bottom: 1rem;
      background: #fafafa;
    }
    textarea { min-height: 80px; resize: vertical; }
    input:focus, textarea:focus { outline: 2px solid #2563eb; border-color: #2563eb; background: #fff; }
    button {
      padding: 0.65rem 1.6rem;
      background: #2563eb;
      color: #fff;
      border: none;
      border-radius: 6px;
      font-size: 1rem;
      font-weight: 600;
      cursor: pointer;
    }
    button:hover { background: #1d4ed8; }
    button:disabled { background: #93c5fd; cursor: not-allowed; }

    #status { margin: 1rem 0; font-size: 0.95rem; color: #555; min-height: 1.4em; }
    #error-box {
      display: none;
      background: #fef2f2;
      border: 1px solid #fca5a5;
      border-radius: 6px;
      padding: 1rem;
      color: #b91c1c;
      margin-bottom: 1rem;
    }

    #output { display: none; }

    .meta-row { display: flex; flex-wrap: wrap; gap: 1rem; margin-bottom: 1rem; }
    .meta-item { flex: 1; min-width: 200px; }
    .meta-label { font-size: 0.75rem; font-weight: 700; text-transform: uppercase; color: #888; margin-bottom: 0.2rem; }
    .meta-value { font-size: 0.95rem; color: #222; word-break: break-all; }

    .keywords { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-top: 0.3rem; }
    .keyword-tag {
      background: #eff6ff;
      color: #1d4ed8;
      border: 1px solid #bfdbfe;
      border-radius: 4px;
      padding: 0.15rem 0.5rem;
      font-size: 0.8rem;
    }

    .blog-card {
      background: #fff;
      border: 1px solid #e0e0e0;
      border-radius: 8px;
      padding: 2rem;
      margin-bottom: 1rem;
      white-space: pre-wrap;
      font-family: Georgia, 'Times New Roman', serif;
      font-size: 1.05rem;
      line-height: 1.8;
      color: #1a1a1a;
    }

    .stats-row { display: flex; flex-wrap: wrap; gap: 1rem; margin-bottom: 1rem; }
    .stat-pill {
      background: #f0fdf4;
      border: 1px solid #bbf7d0;
      border-radius: 6px;
      padding: 0.4rem 0.8rem;
      font-size: 0.85rem;
      color: #166534;
    }
    .stat-pill.warn { background: #fefce8; border-color: #fde68a; color: #854d0e; }
    .stat-pill.danger { background: #fef2f2; border-color: #fca5a5; color: #b91c1c; }

    .action-row { display: flex; flex-wrap: wrap; gap: 0.6rem; margin-bottom: 1rem; }
    .btn-secondary {
      padding: 0.5rem 1rem;
      background: #f1f5f9;
      color: #1e293b;
      border: 1px solid #cbd5e1;
      border-radius: 6px;
      font-size: 0.9rem;
      font-weight: 600;
      cursor: pointer;
    }
    .btn-secondary:hover { background: #e2e8f0; }

    details { margin-bottom: 0.8rem; }
    summary {
      cursor: pointer;
      font-weight: 600;
      font-size: 0.9rem;
      color: #555;
      padding: 0.5rem 0;
      user-select: none;
    }
    summary:hover { color: #222; }
    .details-body {
      background: #f8f9fa;
      border: 1px solid #e0e0e0;
      border-radius: 6px;
      padding: 1rem;
      margin-top: 0.4rem;
      font-size: 0.85rem;
      white-space: pre-wrap;
      overflow-x: auto;
    }
    .source-list { list-style: none; padding: 0; }
    .source-list li { padding: 0.3rem 0; border-bottom: 1px solid #eee; font-size: 0.85rem; }
    .source-list li:last-child { border-bottom: none; }
  </style>
</head>
<body>
<div class="container">
  <h1>BlogAgent</h1>
  <p class="subtitle">Source-grounded blog post generator</p>

  <div class="form-card">
    <label for="secret">Worker Secret <span style="font-weight:400;color:#888">(leave blank if not configured)</span></label>
    <input type="password" id="secret" placeholder="Optional: enter BLOGAGENT_WORKER_SECRET" autocomplete="current-password" />

    <label for="topic">Topic</label>
    <textarea id="topic" placeholder="e.g. Why elephants are the heaviest land animals"></textarea>

    <button id="gen-btn" onclick="generate()">Generate Blog Post</button>
  </div>

  <div id="status"></div>
  <div id="error-box"></div>

  <div id="output">
    <div class="form-card">
      <div id="title-display" style="font-size:1.5rem;font-weight:700;margin-bottom:0.5rem;"></div>

      <div class="meta-row">
        <div class="meta-item">
          <div class="meta-label">Slug</div>
          <div class="meta-value" id="slug-display"></div>
        </div>
        <div class="meta-item">
          <div class="meta-label">Meta Description</div>
          <div class="meta-value" id="meta-display"></div>
        </div>
      </div>

      <div class="meta-item" style="margin-bottom:1rem;">
        <div class="meta-label">SEO Keywords</div>
        <div class="keywords" id="keywords-display"></div>
      </div>

      <div class="stats-row" id="stats-row"></div>

      <div class="action-row">
        <button class="btn-secondary" onclick="copyMarkdown()">Copy article markdown</button>
        <button class="btn-secondary" onclick="downloadMd()">Download .md</button>
        <button class="btn-secondary" onclick="downloadJson()">Download full JSON</button>
      </div>
    </div>

    <div class="blog-card" id="article-display"></div>

    <details id="sources-details">
      <summary id="sources-summary">Sources</summary>
      <div class="details-body"><ul class="source-list" id="sources-list"></ul></div>
    </details>

    <details id="warnings-details" style="display:none">
      <summary>Warnings</summary>
      <div class="details-body" id="warnings-body"></div>
    </details>

    <details>
      <summary>Provider Events</summary>
      <div class="details-body" id="events-body"></div>
    </details>

    <details>
      <summary>Raw JSON</summary>
      <div class="details-body" id="raw-json"></div>
    </details>
  </div>
</div>

<script>
  let _lastResponse = null;
  let _lastTopic = "";

  async function generate() {
    const secret = document.getElementById('secret').value.trim();
    const topic = document.getElementById('topic').value.trim();
    if (!topic) { showError('Please enter a topic.'); return; }

    clearOutput();
    setStatus('Generating blog post…');
    document.getElementById('gen-btn').disabled = true;

    try {
      const resp = await fetch('/run', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(secret ? {'X-BlogAgent-Secret': secret} : {})
        },
        body: JSON.stringify({topic})
      });

      const data = await resp.json();

      if (resp.status === 401) {
        showError('Worker secret is missing or incorrect.');
        return;
      }
      if (!resp.ok) {
        showError('Error ' + resp.status + ': ' + (data.detail || JSON.stringify(data)));
        return;
      }

      _lastResponse = data;
      _lastTopic = topic;
      renderOutput(data);
      setStatus('');
    } catch (err) {
      showError('Network error: ' + err.message);
    } finally {
      document.getElementById('gen-btn').disabled = false;
    }
  }

  function renderOutput(d) {
    if (d.blocked) {
      showError('Request blocked: ' + (d.block_reason || 'publishing requests are not allowed.'));
      return;
    }

    document.getElementById('title-display').textContent = d.title || '(no title)';
    document.getElementById('slug-display').textContent = d.slug || '';
    document.getElementById('meta-display').textContent = d.meta_description || '';

    const kwDiv = document.getElementById('keywords-display');
    kwDiv.innerHTML = '';
    (d.seo_keywords || []).forEach(kw => {
      const span = document.createElement('span');
      span.className = 'keyword-tag';
      span.textContent = kw;
      kwDiv.appendChild(span);
    });

    // Stats
    const statsRow = document.getElementById('stats-row');
    statsRow.innerHTML = '';
    addStat(statsRow, d.source_count + ' source' + (d.source_count !== 1 ? 's' : ''), 'ok');
    const counts = d.claim_status_counts || {};
    addStat(statsRow, (counts.supported || 0) + ' supported', 'ok');
    if (counts.partially_supported) addStat(statsRow, counts.partially_supported + ' partial', 'warn');
    if (counts.unsupported) addStat(statsRow, counts.unsupported + ' unsupported', 'danger');
    addStat(statsRow, d.revision_count + ' revision' + (d.revision_count !== 1 ? 's' : ''), 'ok');
    addStat(statsRow, d.execution_mode || 'mock', 'ok');

    // Article
    document.getElementById('article-display').textContent = d.article_markdown || '';

    // Warnings
    if (d.warnings && d.warnings.length) {
      document.getElementById('warnings-details').style.display = '';
      document.getElementById('warnings-body').textContent = d.warnings.join('\\n');
    }

    // Provider events
    document.getElementById('events-body').textContent =
      (d.provider_events || []).join('\\n') || '(none)';

    // Raw JSON
    document.getElementById('raw-json').textContent = JSON.stringify(d, null, 2);

    // Sources — from source_count (we don't have the list in the compact response)
    const srcSummary = document.getElementById('sources-summary');
    srcSummary.textContent = 'Sources (' + (d.source_count || 0) + ')';
    const srcList = document.getElementById('sources-list');
    srcList.innerHTML = '<li style="color:#888;font-style:italic">Source URLs are not included in the compact API response. Use the CLI with --json for full source details.</li>';

    document.getElementById('output').style.display = '';
  }

  function addStat(parent, text, type) {
    const el = document.createElement('span');
    el.className = 'stat-pill' + (type === 'warn' ? ' warn' : type === 'danger' ? ' danger' : '');
    el.textContent = text;
    parent.appendChild(el);
  }

  function copyMarkdown() {
    if (!_lastResponse) return;
    navigator.clipboard.writeText(_lastResponse.article_markdown || '')
      .then(() => setStatus('Copied to clipboard.'))
      .catch(() => setStatus('Copy failed — use the raw JSON instead.'));
  }

  function downloadMd() {
    if (!_lastResponse) return;
    const slug = _lastResponse.slug || _lastTopic.replace(/\\s+/g, '-').toLowerCase() || 'blog-post';
    download(slug + '.md', _lastResponse.article_markdown || '', 'text/markdown');
  }

  function downloadJson() {
    if (!_lastResponse) return;
    const slug = _lastResponse.slug || _lastTopic.replace(/\\s+/g, '-').toLowerCase() || 'blog-post';
    download(slug + '.json', JSON.stringify(_lastResponse, null, 2), 'application/json');
  }

  function download(filename, content, type) {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([content], {type}));
    a.download = filename;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  function setStatus(msg) {
    document.getElementById('status').textContent = msg;
  }

  function showError(msg) {
    const el = document.getElementById('error-box');
    el.textContent = msg;
    el.style.display = '';
    setStatus('');
  }

  function clearOutput() {
    document.getElementById('error-box').style.display = 'none';
    document.getElementById('error-box').textContent = '';
    document.getElementById('output').style.display = 'none';
    document.getElementById('warnings-details').style.display = 'none';
  }
</script>
</body>
</html>"""


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
