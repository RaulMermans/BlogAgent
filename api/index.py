"""Vercel-compatible FastAPI entry point for BlogAgent.

Exposes a minimal, mock-safe API for serverless deployment.
All routes default to mock mode — no API keys required.

Routes:
    GET  /              → browser UI (HTML) — main entry point
    GET  /app           → browser UI (HTML) — alias for /
    GET  /info          → service info JSON
    GET  /health        → service status
    GET  /auth-status   → whether a worker secret is required (public)
    POST /auth/verify   → verify a submitted worker secret
    GET  /run           → browser-friendly: no topic → usage hint; topic param → run pipeline
    POST /run           → run the BlogAgent pipeline on a topic (JSON body)

Worker secret (optional):
    Set BLOGAGENT_WORKER_SECRET to require a secret on /run endpoints.
    Pass via header X-BlogAgent-Secret, JSON body field worker_secret,
    or query param worker_secret (GET /run only).
    /health, /, /app, /info, and /auth-status remain public regardless.

Safety:
- Publishing requests are blocked by the pipeline guardrail.
- Raw scraped webpage text is never returned.
- No persistence or external side effects in mock mode.
"""

from __future__ import annotations

import os
import secrets
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


class AuthVerifyRequest(BaseModel):
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
    # Extended fields (optional for backward compatibility)
    selected_skills: list[str] = []
    quality_evaluation: dict[str, Any] = {}
    revision_summary: str = ""
    source_quality_scores: list[dict[str, Any]] = []
    requested_count: int | None = None
    final_validation_warnings: list[str] = []
    run_trace: list[str] = []


# ---------------------------------------------------------------------------
# Worker secret guard
# ---------------------------------------------------------------------------


def _worker_secret_required() -> str:
    """Return the configured worker secret, or '' if no secret is required."""
    return os.environ.get("BLOGAGENT_WORKER_SECRET", "").strip()


def _secrets_match(provided: str, expected: str) -> bool:
    """Constant-time comparison of two secret strings."""
    return secrets.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


def _check_worker_secret(request: Request, body_secret: str = "", query_secret: str = "") -> None:
    """Raise 401 if BLOGAGENT_WORKER_SECRET is set and the request doesn't match.

    Checks (in order): X-BlogAgent-Secret header, body field, query param.
    Does nothing when the env var is unset or empty.
    Uses constant-time comparison.
    """
    required = _worker_secret_required()
    if not required:
        return

    header_secret = request.headers.get("X-BlogAgent-Secret", "")
    provided = header_secret or body_secret or query_secret

    if not _secrets_match(provided, required):
        raise HTTPException(status_code=401, detail="Invalid or missing worker secret")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
def root() -> HTMLResponse:
    return HTMLResponse(content=_build_app_html())


@app.get("/app", response_class=HTMLResponse)
def app_ui() -> HTMLResponse:
    return HTMLResponse(content=_build_app_html())


@app.get("/info")
def info() -> dict[str, Any]:
    return {
        "service": "BlogAgent",
        "status": "ok",
        "description": "Source-grounded editorial agent API",
        "endpoints": {
            "health": "GET /health",
            "app": "GET / or GET /app",
            "info": "GET /info",
            "auth_status": "GET /auth-status",
            "auth_verify": "POST /auth/verify",
            "run_post": "POST /run",
            "run_get": "GET /run?topic=...",
        },
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "BlogAgent", "mode": "mock-safe"}


@app.get("/auth-status")
def auth_status() -> dict[str, bool]:
    return {"worker_secret_required": bool(_worker_secret_required())}


@app.post("/auth/verify")
def auth_verify(request: Request, body: AuthVerifyRequest) -> dict[str, bool]:
    """Validate the worker secret. Returns 200 if valid, 401 if not.

    Accepts the secret via JSON body or X-BlogAgent-Secret header.
    """
    required = _worker_secret_required()
    if not required:
        return {"ok": True, "worker_secret_required": False}
    header_secret = request.headers.get("X-BlogAgent-Secret", "")
    provided = header_secret or body.worker_secret or ""
    if not _secrets_match(provided, required):
        raise HTTPException(status_code=401, detail="Invalid or missing worker secret")
    return {"ok": True, "worker_secret_required": True}


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
            run_trace=list(state.run_trace),
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
        selected_skills=list(state.selected_skills),
        quality_evaluation=dict(state.quality_evaluation) if state.quality_evaluation else {},
        revision_summary=state.revision_summary or "",
        source_quality_scores=list(state.source_quality_scores),
        requested_count=state.requested_count,
        final_validation_warnings=list(state.final_validation_warnings),
        run_trace=list(state.run_trace),
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

    .hint {
      font-size: 0.82rem;
      color: #888;
      margin-bottom: 1rem;
      font-style: italic;
    }
    .logged-in-row {
      display: flex;
      align-items: center;
      gap: 1rem;
      flex-wrap: wrap;
    }
    .logged-in-label {
      font-size: 0.9rem;
      color: #166534;
      font-weight: 600;
    }
    .btn-logout {
      padding: 0.4rem 0.9rem;
      background: #f1f5f9;
      color: #1e293b;
      border: 1px solid #cbd5e1;
      border-radius: 6px;
      font-size: 0.85rem;
      font-weight: 600;
      cursor: pointer;
    }
    .btn-logout:hover { background: #e2e8f0; }

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

    #output-section { display: none; }
    #authenticated-app { display: none; }

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

    .quality-badge {
      display: inline-block;
      font-size: 0.7rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      padding: 0.1rem 0.4rem;
      border-radius: 4px;
      margin-left: 0.4rem;
      vertical-align: middle;
    }
    .quality-badge.high { background: #dcfce7; color: #166534; border: 1px solid #86efac; }
    .quality-badge.medium { background: #fef9c3; color: #713f12; border: 1px solid #fde047; }
    .quality-badge.low { background: #fee2e2; color: #991b1b; border: 1px solid #fca5a5; }

    .trace-list { list-style: none; padding: 0; }
    .trace-list li { padding: 0.25rem 0; font-size: 0.85rem; font-family: monospace; border-bottom: 1px solid #eee; }
    .trace-list li:last-child { border-bottom: none; }
    .trace-list li.ok { color: #166534; }
    .trace-list li.warn { color: #854d0e; }
    .trace-list li.blocked { color: #b91c1c; }

    .skill-tag {
      display: inline-block;
      background: #f0f9ff;
      color: #0369a1;
      border: 1px solid #bae6fd;
      border-radius: 4px;
      padding: 0.15rem 0.5rem;
      font-size: 0.78rem;
      margin: 0.15rem 0.2rem 0.15rem 0;
    }

    #loader-status {
      display: none;
      margin: 1rem 0;
      font-size: 0.95rem;
      color: #2563eb;
      font-weight: 500;
    }
    .loader-dot { display: inline-block; animation: blink 1.2s infinite; }
    .loader-dot:nth-child(2) { animation-delay: 0.2s; }
    .loader-dot:nth-child(3) { animation-delay: 0.4s; }
    @keyframes blink { 0%,80%,100% { opacity: 0; } 40% { opacity: 1; } }
  </style>
</head>
<body>
<div class="container">
  <h1>BlogAgent</h1>
  <p class="subtitle">Source-grounded blog post generator</p>

  <!-- access-screen: visible by default; hidden after successful auth -->
  <div id="access-screen" class="form-card">
    <label for="secret-input">Worker Secret</label>
    <input type="password" id="secret-input" placeholder="Enter worker secret (or leave blank if not configured)" autocomplete="current-password" />
    <p class="hint">Private demo access. This is a lightweight gate, not production auth. The secret is stored in sessionStorage for this browser session only.</p>
    <button type="button" onclick="login()">Login</button>
    <p id="access-message" style="font-size:0.9rem;color:#b91c1c;margin-top:0.5rem;min-height:1.2em;"></p>
  </div>

  <!-- authenticated-app: hidden by default; revealed after successful auth -->
  <div id="authenticated-app" style="display:none">
    <p id="auth-state" style="font-size:0.85rem;color:#166534;font-weight:600;margin-bottom:0.5rem;">Logged in</p>

    <div class="form-card" style="margin-bottom:1rem;">
      <div class="logged-in-row">
        <span class="logged-in-label">Logged in</span>
        <button class="btn-logout" type="button" onclick="logout()">Logout / Clear Secret</button>
      </div>
    </div>

    <div id="api-health" style="font-size:0.82rem;color:#888;margin-bottom:0.5rem;">API health: checking…</div>

    <div class="form-card">
      <label for="topic">Topic</label>
      <textarea id="topic" placeholder="e.g. Why elephants are the heaviest land animals"></textarea>
      <button type="button" id="generateButton">Generate Blog Post</button>
    </div>

    <div id="status"></div>
    <div id="loader-status"><span id="loader-stage">Planning article</span><span class="loader-dot">.</span><span class="loader-dot">.</span><span class="loader-dot">.</span></div>
    <div id="error-box"></div>

    <details style="margin-bottom:0.8rem;">
      <summary>Debug</summary>
      <pre id="debugOutput" class="details-body" style="margin-top:0.4rem;"></pre>
    </details>

    <section id="output-section" style="display:none;">
      <h2 style="font-size:1.3rem;font-weight:700;margin-bottom:1rem;">Generated Blog Post</h2>
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
          <button class="btn-secondary" type="button" onclick="copyMarkdown()">Copy article markdown</button>
          <button class="btn-secondary" type="button" onclick="downloadMd()">Download .md</button>
          <button class="btn-secondary" type="button" onclick="downloadJson()">Download full JSON</button>
        </div>
      </div>

      <div class="blog-card" id="article-display"></div>

      <details id="sources-details">
        <summary id="sources-summary">Sources</summary>
        <div class="details-body"><ul class="source-list" id="sources-list"></ul></div>
      </details>

      <details id="trace-details" style="display:none">
        <summary>Agent Run Trace</summary>
        <div class="details-body"><ul class="trace-list" id="trace-list"></ul></div>
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
        <pre class="details-body" id="raw-json"></pre>
      </details>
    </section>
  </div>
</div>

<script>
  const SECRET_KEY = 'blogagent_worker_secret';
  let auth_verified = false;
  let _lastResponse = null;
  let _lastTopic = "";

  function showAccessScreen(message) {
    document.getElementById('access-screen').style.display = 'block';
    document.getElementById('authenticated-app').style.display = 'none';
    auth_verified = false;
    document.getElementById('access-message').textContent = message !== undefined ? message : '';
    clearOutput();
  }

  function showAuthenticatedApp(message) {
    document.getElementById('access-screen').style.display = 'none';
    document.getElementById('authenticated-app').style.display = 'block';
    auth_verified = true;
    document.getElementById('auth-state').textContent = message || 'Logged in';
  }

  async function init() {
    document.getElementById('generateButton').addEventListener('click', generate);
    checkHealth();
    // Clear any stale legacy localStorage entries from earlier versions.
    try {
      localStorage.removeItem(SECRET_KEY);
      localStorage.removeItem('blogagent_secret_saved');
    } catch (_) {}
    try {
      const resp = await fetch('/auth-status');
      const data = await resp.json();
      if (!data.worker_secret_required) {
        showAuthenticatedApp('No worker secret configured');
        return;
      }
      const stored = sessionStorage.getItem(SECRET_KEY);
      if (!stored) {
        showAccessScreen('Login required');
        return;
      }

      const verifyResp = await fetch('/auth/verify', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({worker_secret: stored})
      });
      if (verifyResp.ok) {
        showAuthenticatedApp('Logged in');
      } else {
        sessionStorage.removeItem(SECRET_KEY);
        showAccessScreen('Login required');
      }
    } catch (_) {
      showAccessScreen('Login required');
    }
  }

  async function login() {
    const val = document.getElementById('secret-input').value;
    try {
      const resp = await fetch('/auth/verify', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({worker_secret: val})
      });
      if (resp.ok) {
        sessionStorage.setItem(SECRET_KEY, val);
        showAuthenticatedApp('Logged in');
      } else {
        showAccessScreen('Invalid or missing worker secret');
      }
    } catch (_) {
      showAccessScreen('Login required');
    }
  }

  function logout() {
    sessionStorage.removeItem(SECRET_KEY);
    document.getElementById('secret-input').value = '';
    showAccessScreen('');
  }

  async function checkHealth() {
    const el = document.getElementById('api-health');
    try {
      const resp = await fetch('/health');
      if (resp.ok) {
        el.textContent = 'API health: ok';
        el.style.color = '#166534';
      } else {
        el.textContent = 'API health: unavailable';
        el.style.color = '#b91c1c';
      }
    } catch (_) {
      el.textContent = 'API health: unavailable';
      el.style.color = '#b91c1c';
    }
  }

  const LOADER_STAGES = [
    'Planning article',
    'Selecting editorial skills',
    'Searching sources',
    'Scoring source quality',
    'Building evidence table',
    'Drafting article',
    'Evaluating quality',
    'Revising weak sections',
    'Packaging final post',
  ];
  let _loaderTimer = null;
  let _loaderIdx = 0;

  function startLoader() {
    _loaderIdx = 0;
    const stageEl = document.getElementById('loader-stage');
    const loaderEl = document.getElementById('loader-status');
    loaderEl.style.display = 'block';
    stageEl.textContent = LOADER_STAGES[0];
    _loaderTimer = setInterval(() => {
      _loaderIdx = (_loaderIdx + 1) % LOADER_STAGES.length;
      stageEl.textContent = LOADER_STAGES[_loaderIdx];
    }, 2000);
  }

  function stopLoader() {
    if (_loaderTimer) { clearInterval(_loaderTimer); _loaderTimer = null; }
    document.getElementById('loader-status').style.display = 'none';
  }

  async function generate() {
    const secret = sessionStorage.getItem(SECRET_KEY) || '';
    const topic = document.getElementById('topic').value.trim();
    if (!topic) { showError('Please enter a topic'); return; }

    clearOutput();
    setStatus('');
    startLoader();
    document.getElementById('generateButton').disabled = true;

    const debugInfo = {
      url: '/run',
      status: null,
      error: null,
      auth_verified: auth_verified,
      secret_sent: secret.length > 0
    };

    try {
      const resp = await fetch('/run', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-BlogAgent-Secret': secret
        },
        body: JSON.stringify({topic})
      });

      debugInfo.status = resp.status;

      let data;
      try { data = await resp.json(); } catch (_) { data = {}; }

      if (resp.status === 401) {
        debugInfo.error = 'Invalid or missing worker secret';
        setDebug(debugInfo);
        showError('Invalid or missing worker secret');
        sessionStorage.removeItem(SECRET_KEY);
        showAccessScreen('Session expired. Please login again.');
        return;
      }
      if (!resp.ok) {
        const msg = (data && data.detail) ? data.detail : JSON.stringify(data);
        debugInfo.error = msg;
        setDebug(debugInfo);
        showError('Request failed: ' + resp.status + ' ' + msg);
        return;
      }

      _lastResponse = data;
      _lastTopic = topic;
      setDebug(debugInfo);
      try {
        renderOutput(data);
        setStatus('Success');
      } catch (renderErr) {
        showError('Render error: ' + renderErr.message);
        try {
          document.getElementById('raw-json').textContent = JSON.stringify(data, null, 2);
          document.getElementById('output-section').style.display = 'block';
        } catch (_) {}
      }
    } catch (err) {
      debugInfo.error = err.message;
      setDebug(debugInfo);
      showError('Network error: ' + err.message);
    } finally {
      stopLoader();
      document.getElementById('generateButton').disabled = false;
    }
  }

  function setDebug(info) {
    const el = document.getElementById('debugOutput');
    el.textContent = [
      'url: ' + info.url,
      'status: ' + (info.status !== null ? info.status : 'n/a'),
      'error: ' + (info.error || 'none'),
      'auth_verified: ' + (info.auth_verified === true),
      'secret_sent: ' + (info.secret_sent === true)
    ].join('\\n');
  }

  function renderOutput(data) {
    const title = data.title || 'Untitled Blog Post';
    const slug = data.slug || '';
    const metaDescription = data.meta_description || data.metaDescription || '';
    const seoKeywords = data.seo_keywords || data.seoKeywords || [];
    const articleMarkdown =
      data.article_markdown ||
      data.articleMarkdown ||
      data.markdown ||
      data.article ||
      data.content ||
      '';
    const sourceCount = data.source_count || data.sourceCount || 0;
    const claimStatusCounts = data.claim_status_counts || data.claimStatusCounts || {};
    const providerEvents = data.provider_events || data.providerEvents || [];
    const executionMode = data.execution_mode || data.executionMode || '';
    const selectedSkills = data.selected_skills || [];
    const sourceQualityScores = data.source_quality_scores || [];
    const runTrace = data.run_trace || [];
    const qualityEval = data.quality_evaluation || {};

    if (data.blocked) {
      showError('Request blocked: ' + (data.block_reason || 'publishing requests are not allowed.'));
      return;
    }

    document.getElementById('output-section').style.display = 'block';
    document.getElementById('output-section').scrollIntoView({ behavior: 'smooth', block: 'start' });

    document.getElementById('title-display').textContent = title;
    document.getElementById('slug-display').textContent = slug;
    document.getElementById('meta-display').textContent = metaDescription;

    const kwDiv = document.getElementById('keywords-display');
    kwDiv.innerHTML = '';
    seoKeywords.forEach(kw => {
      const span = document.createElement('span');
      span.className = 'keyword-tag';
      span.textContent = kw;
      kwDiv.appendChild(span);
    });

    const statsRow = document.getElementById('stats-row');
    statsRow.innerHTML = '';
    addStat(statsRow, sourceCount + ' source' + (sourceCount !== 1 ? 's' : ''), 'ok');
    addStat(statsRow, (claimStatusCounts.supported || 0) + ' supported', 'ok');
    if (claimStatusCounts.partially_supported) addStat(statsRow, claimStatusCounts.partially_supported + ' partial', 'warn');
    if (claimStatusCounts.unsupported) addStat(statsRow, claimStatusCounts.unsupported + ' unsupported', 'danger');
    addStat(statsRow, (data.revision_count || 0) + ' revision' + ((data.revision_count || 0) !== 1 ? 's' : ''), 'ok');
    addStat(statsRow, executionMode || 'mock', 'ok');
    if (qualityEval && qualityEval.score !== undefined) {
      const qType = qualityEval.passes ? 'ok' : 'warn';
      addStat(statsRow, 'quality ' + qualityEval.score + '/100', qType);
    }

    // Skills row
    if (selectedSkills.length) {
      const skillsDiv = document.createElement('div');
      skillsDiv.style.marginBottom = '0.8rem';
      const skillsLabel = document.createElement('div');
      skillsLabel.className = 'meta-label';
      skillsLabel.textContent = 'Editorial Skills';
      skillsDiv.appendChild(skillsLabel);
      selectedSkills.forEach(sk => {
        const span = document.createElement('span');
        span.className = 'skill-tag';
        span.textContent = sk;
        skillsDiv.appendChild(span);
      });
      document.getElementById('title-display').closest('.form-card').appendChild(skillsDiv);
    }

    document.getElementById('article-display').textContent = articleMarkdown || 'No article markdown returned by API.';

    if (data.warnings && data.warnings.length) {
      document.getElementById('warnings-details').style.display = '';
      document.getElementById('warnings-body').textContent = data.warnings.join('\\n');
    }

    document.getElementById('events-body').textContent = providerEvents.join('\\n') || '(none)';

    document.getElementById('raw-json').textContent = JSON.stringify(data, null, 2);

    // Sources with quality badges
    const srcSummary = document.getElementById('sources-summary');
    srcSummary.textContent = 'Sources (' + sourceCount + ')';
    const srcList = document.getElementById('sources-list');
    if (sourceQualityScores.length) {
      srcList.innerHTML = '';
      sourceQualityScores.forEach(sq => {
        const li = document.createElement('li');
        const badge = '<span class="quality-badge ' + (sq.quality || 'medium') + '">' + (sq.quality || '?') + '</span>';
        const titleText = sq.title ? sq.title : (sq.url || '');
        li.innerHTML = badge + ' ' + escapeHtml(titleText);
        if (sq.reason) {
          const small = document.createElement('span');
          small.style.cssText = 'color:#888;margin-left:0.5rem;font-size:0.78rem;';
          small.textContent = '— ' + sq.reason;
          li.appendChild(small);
        }
        srcList.appendChild(li);
      });
    } else {
      srcList.innerHTML = '<li style="color:#888;font-style:italic">Source URLs are not included in the compact API response. Use the CLI with --json for full source details.</li>';
    }

    // Agent Run Trace
    if (runTrace.length) {
      document.getElementById('trace-details').style.display = '';
      const traceList = document.getElementById('trace-list');
      traceList.innerHTML = '';
      runTrace.forEach(line => {
        const li = document.createElement('li');
        li.textContent = line;
        if (line.startsWith('✓')) li.className = 'ok';
        else if (line.startsWith('⚠')) li.className = 'warn';
        else if (line.startsWith('✗')) li.className = 'blocked';
        traceList.appendChild(li);
      });
    }

  }

  function escapeHtml(str) {
    return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
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
    document.getElementById('output-section').style.display = 'none';
    document.getElementById('warnings-details').style.display = 'none';
    document.getElementById('trace-details').style.display = 'none';
    document.getElementById('trace-list').innerHTML = '';
    document.getElementById('sources-list').innerHTML = '';
    // Remove any dynamically injected skills rows from prior runs
    const skillDivs = document.querySelectorAll('.form-card .meta-label');
    skillDivs.forEach(el => { if (el.textContent === 'Editorial Skills') el.closest('div').remove(); });
  }

  document.addEventListener('DOMContentLoaded', init);
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
