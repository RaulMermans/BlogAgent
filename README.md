# BlogAgent

A source-grounded editorial agent that turns a user topic into a researched, fact-checked, SEO-ready blog post.

This is not a generic AI blog generator. It is an agentic editorial workflow with web research, source extraction, source scoring, evidence tables, claim extraction, citation matching, evaluator-based revision, and final article packaging.

**Primary goal:** produce trustworthy blog drafts with visible research traces and claim-level support.

---

## Implementation Status

| Layer | Status |
|---|---|
| Deterministic pipeline scaffold | **Done** |
| Schema validation + guardrails | **Done** |
| External side-effect blocking | **Done** |
| Mock search + extraction (default) | **Done** |
| Real search via Tavily (opt-in) | **Done** — requires `TAVILY_API_KEY` |
| Real webpage extraction via httpx+BS4 | **Done** — runs on non-mock URLs |
| Deterministic source scoring | **Done** |
| LLM client layer (mock default; Anthropic/OpenAI/Google optional) | **Done** |
| Editor Agent (research plan, outline, draft, revision) | **Done** — mock by default; LLM-gated via env |
| Fact-Check Evaluator (claim extraction + judgment) | **Done** — mock by default; LLM-gated via env |
| Runtime skill registry (6 skills, prompt injection) | **Done** |
| Deterministic skill selection | **Done** |
| Quality Evaluator (deterministic, 10 checks) | **Done** |
| Quality-driven Revision Agent | **Done** — mock by default; LLM-gated via env |
| Final quality validator (post-revision, warns not blocks) | **Done** |
| Source quality scoring (domain heuristic, high/medium/low) | **Done** |
| Heuristic claim extraction | **Done** |
| Revision loop (max 1) | **Done** |
| Heuristic citation matching (deterministic) | **Done** |
| Optional LLM semantic citation judge | **Done** — opt-in via `BLOGAGENT_USE_LLM_CITATION_JUDGE=true` |
| Mock/live output comparison CLI | **Done** |
| GitHub Actions CI | **Done** — mock mode, no API keys required |
| Vercel API scaffold | **Done** — mock-safe by default |
| Agent Run Trace UI panel | **Done** |
| Source quality badges in UI | **Done** |
| Staged workflow animation (12 steps, self-annotating) | **Done** |
| Persistence / database | Not yet |

---

## MVP Architecture

The pipeline uses a **hybrid deterministic workflow** with two model roles:

### Agents

| Agent | Role |
|---|---|
| **Editor Agent** | Research planning, outline, draft, revision |
| **Fact-Check Evaluator** | Claim extraction, citation classification |

### Tools

| Tool | Permission | Purpose |
|---|---|---|
| `web_search` | read_only | Search for sources (mock default; Tavily optional) |
| `webpage_extract` | read_only | Extract text from source URLs (httpx + BS4) |
| `source_score` | read_only | Score sources deterministically |
| `claim_extractor` | read_only | Extract factual claims from the draft |
| `citation_matcher` | read_only | Match claims to evidence sources |
| `validators` | read_only | Deterministic validation of the final package |

### Workflow

```text
User Topic
→ Intake Parser
→ check_external_effects   (guardrail — blocks publishing requests; extracts requested_count)
→ select_skills            (deterministic: recommendation / financial / factual)
→ Editor Agent research plan  (skill briefs injected)
→ web_search
→ webpage_extract
→ source_score
→ score_source_quality     (high/medium/low per domain)
→ Evidence Table Builder
→ Editor Agent outline     (skill briefs injected)
→ Editor Agent draft       (skill briefs injected)
→ Quality Evaluator        (10 deterministic checks; scores 0–100; score capped at 69 on HIGH defect)
→ [if HIGH-severity defect and revision_count < 1]
    → Revision Agent       (quality-driven; mock or LLM)
→ final_validate_quality   (post-revision check — sets final_validation_status and final_validation_defects)
→ [if final_validation_status=failed and fixable HIGH defect and revision_count < 1]
    → Revision Agent       (final-validation-triggered; at most one revision total)
    → final_validate_quality re-runs
→ claim_extractor
→ citation_matcher
→ Fact-Check Evaluator
→ [if not passed and revision_count < 1]
    → Editor Agent revision
    → claim_extractor + citation_matcher + fact-check (re-run)
→ blog_package_validator
→ Final Article Package
```

The final `ArticlePackage` always contains:
- Article markdown
- Source list with scores
- Fact-check report
- Claim support statuses
- Revision summary
- SEO fields: `title`, `slug`, `meta_description`, `seo_keywords`

Publishing to external systems is **blocked in MVP** and requires explicit user approval.

---

## Install

Requires Python 3.11+.

```bash
# With uv (recommended)
uv sync

# With pip (installs runtime + dev extras)
pip install -e ".[dev]"
```

---

## Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

### LLM provider variables

| Variable | Default | Purpose |
|---|---|---|
| `BLOGAGENT_LLM_PROVIDER` | `mock` | `mock` (no key needed), `anthropic`, `openai`, or `google` |
| `BLOGAGENT_LLM_MODEL` | _(provider default)_ | Override model name (takes priority over provider-specific model vars) |
| `BLOGAGENT_LLM_TIMEOUT_SECONDS` | `60` | Timeout for LLM API calls |
| `ANTHROPIC_API_KEY` | _(empty)_ | Required when provider is `anthropic` |
| `OPENAI_API_KEY` | _(empty)_ | Required when provider is `openai` |
| `GOOGLE_API_KEY` | _(empty)_ | Required when provider is `google` |
| `BLOGAGENT_GOOGLE_MODEL` | `gemini-2.5-flash` | Google model when `BLOGAGENT_LLM_MODEL` is not set |
| `BLOGAGENT_USE_LLM_EDITOR` | `false` | Enable real LLM calls for Editor Agent |
| `BLOGAGENT_USE_LLM_FACTCHECK` | `false` | Enable real LLM calls for Fact-Check Evaluator |
| `BLOGAGENT_USE_LLM_CITATION_JUDGE` | `false` | Enable LLM semantic per-claim citation verification (incurs API cost) |

**Fallback transparency:** If a provider is configured but the API key is missing or the
package is not installed, the system falls back to mock with an explicit warning — no crash.
The warning appears in `state.warnings` and in `provider_events` (visible via `--show-trace`).
`execution_mode` reflects what **actually ran**, not what env vars requested.

**Recommended affordable live provider:** Google Gemini (`BLOGAGENT_LLM_PROVIDER=google`).

### Search provider variables

| Variable | Default | Purpose |
|---|---|---|
| `BLOGAGENT_SEARCH_PROVIDER` | `mock` | `mock` for deterministic tests; `tavily` for real search |
| `TAVILY_API_KEY` | _(empty)_ | Required when provider is `tavily` |
| `BLOGAGENT_HTTP_TIMEOUT_SECONDS` | `15` | Timeout for web requests |
| `BLOGAGENT_MAX_SEARCH_RESULTS` | `5` | Max results per query |

---

## Run Tests

All tests run without API keys.

```bash
# With uv
uv run pytest

# With pytest directly
pytest
```

---

## Run the App

```bash
uv run streamlit run app/ui/streamlit_app.py
```

---

## Run Evals

```bash
uv run python -m blogagent.evals.runner
```

---

## Live Smoke Test

The CLI provides a single-run smoke test with configurable provider modes. All examples
below are safe to run — they do not publish externally and do not require API keys in
mock mode.

### Mock mode (default — no API keys needed)

```bash
uv run python -m blogagent.cli run "Why elephants are the heaviest land animals" --show-trace
```

Prints a summary with title, source count, claim stats, revision count, execution mode,
and (with `--show-trace`) the full provider event log and stage timings.

### Google live editor (recommended affordable provider)

```bash
BLOGAGENT_LLM_PROVIDER=google \
BLOGAGENT_USE_LLM_EDITOR=true \
GOOGLE_API_KEY=your_key_here \
uv run python -m blogagent.cli run "Why elephants are the heaviest land animals" --show-trace
```

### Google low-cost mode

```bash
BLOGAGENT_LLM_PROVIDER=google \
BLOGAGENT_USE_LLM_EDITOR=true \
GOOGLE_API_KEY=your_key_here \
BLOGAGENT_GOOGLE_MODEL=gemini-2.5-flash-lite \
uv run python -m blogagent.cli run "Why elephants are the heaviest land animals" --show-trace
```

### Anthropic editor only

```bash
BLOGAGENT_LLM_PROVIDER=anthropic \
BLOGAGENT_USE_LLM_EDITOR=true \
ANTHROPIC_API_KEY=your_key_here \
uv run python -m blogagent.cli run "Why elephants are the heaviest land animals" --show-trace
```

### Tavily search + Anthropic editor + Anthropic fact-check

```bash
BLOGAGENT_SEARCH_PROVIDER=tavily \
TAVILY_API_KEY=your_key_here \
BLOGAGENT_LLM_PROVIDER=anthropic \
BLOGAGENT_USE_LLM_EDITOR=true \
BLOGAGENT_USE_LLM_FACTCHECK=true \
ANTHROPIC_API_KEY=your_key_here \
uv run python -m blogagent.cli run "Why elephants are the heaviest land animals" --show-trace
```

### Output flags

```bash
# Print full ArticlePackage as JSON
uv run python -m blogagent.cli run "Solar energy trends" --json

# Write JSON output to a file
uv run python -m blogagent.cli run "Solar energy trends" --output examples/live_smoke_output.json
```

Do not include real API keys in committed files or shell history.

---

## Provider benchmark protocol

Before treating a run as a valid live benchmark:

1. Export the provider key: `export GOOGLE_API_KEY=your_key`
2. Run with `--show-trace` and check provider events:
   - All `editor.*` events must show `actual_provider=google` (or `anthropic`/`openai`) and `fallback=false`
   - `warnings` must be empty (warnings indicate unexpected fallbacks)
   - `execution_mode` must be `live` or `hybrid`, not `mock`
3. If any event shows `actual_provider=mock`, that stage used mock data — the run is not a valid live benchmark. Check warnings for the reason.
4. Compare outputs only after confirming real provider execution.

Mock output can appear identical to live output in terms of structure while containing only template prose. Always verify `actual_provider` before drawing quality conclusions.

---

## Comparing mock vs live provider outputs

BlogAgent can compare two or more saved run output JSON files and report a side-by-side
quality summary. This is useful for checking whether switching from mock to a real LLM or
search provider improved output quality.

### Produce output files

```bash
# Mock mode (no API keys needed)
uv run python -m blogagent.cli run "African Elephants" --output examples/my_mock_output.json

# Live mode (requires API keys)
BLOGAGENT_LLM_PROVIDER=anthropic \
BLOGAGENT_USE_LLM_EDITOR=true \
BLOGAGENT_SEARCH_PROVIDER=tavily \
ANTHROPIC_API_KEY=your_key \
TAVILY_API_KEY=your_key \
uv run python -m blogagent.cli run "African Elephants" --output examples/my_live_output.json
```

The `--output` flag writes an enriched JSON that includes the `ArticlePackage` fields plus
state-level metadata: `execution_mode`, `revision_count`, `provider_events`, and `warnings`.

### Compare them

```bash
uv run python -m blogagent.cli compare examples/mock_elephants_output.json examples/live_elephants_output.json
```

Example output:

```
BlogAgent Output Comparison
------------------------------------------------------------------
                                  mock_elephants_output.json      live_elephants_output.json
------------------------------------------------------------------
METADATA
  execution_mode                  mock                      live
  blocked                         False                     False
  revision_count                  0                         1
  provider_events                 5                         5
  warnings                        1                         0

ARTICLE
  has_title                       yes                       yes
  has_meta_description            yes                       yes
  word_count                      283                       682
  heading_count                   5                         6

SOURCES
  total                           3                         4
  mock                            3                         0
  real                            0                         4

CLAIMS
  total                           3                         5
  supported                       0                         4
  partially_supported             3                         1
  unsupported                     0                         0

QUALITY SCORE  (max 100)
  score                           75                        100
  deductions:
    all sources are mock          [x] mock_elephants_output [x] [ ] live_elephants_output
    under 600 words (283)         [x] mock_elephants_output [ ] live_elephants_output
```

### Quality rubric

Scores are deterministic — the same input always produces the same score.
No LLM judge is used.

| Check | Points |
|---|---|
| Valid title | +10 |
| Valid meta description | +10 |
| Article has at least one markdown heading | +10 |
| Article is over 600 words | +15 |
| At least 3 sources | +15 |
| No unsupported high-importance claims | +20 |
| Not all sources are mock placeholders | +10 |
| Revision summary is non-empty | +10 |
| **Total** | **100** |

**Score cap:** If any HIGH-severity defect is present (top-N count mismatch, missing Quick Picks, missing financial disclaimer, etc.), the score is capped at 69 regardless of other checks passing. A score ≥ 70 is required for `passes=True`.

**Evidence-limited exception:** For recommendation articles, if the article explicitly explains that the requested count cannot be met due to limited evidence (and the title does not falsely claim the full count), the top-N count mismatch defect is suppressed. The run trace labels this as `evidence_limited_count_accepted=True`.

The score is a heuristic indicator, not a substitute for editorial review.
See [docs/eval_plan.md](docs/eval_plan.md) for caveats.

---

## CI / Continuous Integration

GitHub Actions runs automatically on every push and pull request.

CI uses **mock mode** — no real API keys are required. The workflow:

1. Checks out the repo
2. Installs `uv` and Python 3.11 / 3.12
3. Runs `uv sync --all-extras`
4. Runs `uv run ruff check .` (lint)
5. Runs `uv run pytest -q` (tests)
6. Runs `uv run python -m blogagent.evals.runner` (evals)

Real provider evals (Tavily search, Anthropic/OpenAI LLM) are **manual and local** until
explicitly configured as repository secrets. Running them in CI requires adding the relevant
API keys as GitHub secrets and overriding the mock-mode env vars in the workflow.

---

## Browser Interface

BlogAgent ships a minimal browser UI. The main app URL is `/` — open it directly:

```
https://blog-agent-liart.vercel.app/
```

`/app` is an alias for the same page. `/info` returns API metadata as JSON.

No framework, no React, no Next.js — just a single FastAPI-rendered HTML page.

### Worker secret login

The interface boots into a **private access screen** when `BLOGAGENT_WORKER_SECRET` is set on the deployment. The topic input and generate tool stay hidden until the user enters the correct secret.

1. On first visit, the page calls `GET /auth-status`. If `worker_secret_required` is `false` (no secret configured), the tool is shown immediately.
2. If a secret is required, you see only the **Worker Secret** input and a **Login** button.
3. Clicking **Login** sends the entered value to `POST /auth/verify`. The server compares it against `BLOGAGENT_WORKER_SECRET` using a constant-time comparison.
4. On `200`, the secret is stored in `sessionStorage` under the key `blogagent_worker_secret` and the UI flips to the authenticated state showing **Logged in**, the topic textarea, and **Generate Blog Post**.
5. On `401`, the UI shows **Invalid or missing worker secret** and stays on the login screen.
6. Each generate request sends the stored secret in the `X-BlogAgent-Secret` header.
7. If `POST /run` returns `401`, the UI clears `sessionStorage`, returns to the login screen, and shows **Session expired or invalid worker secret. Log in again.**
8. To log out, click **Logout** — this clears `sessionStorage` (and any leftover `localStorage` keys from earlier versions).

**This is not production authentication.** Wrong secrets do not unlock the tool. There are no user accounts, sessions, OAuth, cookies, or rate limiting. `sessionStorage` reduces persistence compared to `localStorage` (it's cleared when the tab closes) but is still readable by any script on the same origin — do not use this gate for sensitive credentials.

### What the interface lets you do

- Log in with a worker secret (verified server-side; stored in `sessionStorage`)
- Enter a topic and generate a blog post
- See the title, slug, meta description, SEO keywords, article markdown, and claim/source stats
- Copy the article markdown to clipboard
- Download the article as `.md`
- Download the full JSON response

Provider events and raw JSON are collapsed in `<details>` sections and do not dominate the view.

---

## Troubleshooting

### If the login screen will not unlock

1. Click **Logout** to wipe any stale stored value from `sessionStorage`.
2. Re-enter your worker secret and click **Login**.
3. If you see **Invalid or missing worker secret**, the entered value does not match `BLOGAGENT_WORKER_SECRET` on the deployment — double-check both sides.
4. Expand the **Debug** section (after logging in) and confirm `auth_verified: true` and `secret_sent: true` appear on the next generate attempt.

`sessionStorage` is cleared automatically when the tab closes; older versions of the UI used `localStorage`, and any leftover keys from those versions are wiped on logout.

---

### If clicking Generate does nothing

1. Open Vercel logs (or browser DevTools → Network tab) and check for a `POST /run` request.
2. If no `POST /run` appears in the logs, the frontend JavaScript did not fire — check the browser console (F12) for JavaScript errors.
3. Test `POST /run` directly with curl to rule out a backend issue:
   ```bash
   curl -X POST https://YOUR-VERCEL-URL.vercel.app/run \
     -H "Content-Type: application/json" \
     -H "X-BlogAgent-Secret: your-secret" \
     -d '{"topic":"Why elephants are the heaviest land animals"}'
   ```
4. Confirm the worker secret saved in your browser matches `BLOGAGENT_WORKER_SECRET` on Vercel. A wrong secret returns `401` and clears the saved secret automatically.
5. Expand the **Debug** section on the page — it shows the request URL, response status, any error message, and whether a secret was sent.

---

## Worker Secret

By default `/run` is unprotected. Set `BLOGAGENT_WORKER_SECRET` to add a lightweight
demo gate that prevents casual use of the generation endpoint and locks the browser
UI behind a private access screen:

```bash
BLOGAGENT_WORKER_SECRET=your-secret
```

**Behavior:**

| Env var state | Effect |
|---|---|
| Unset or empty | `/run` works without a secret; the UI shows the tool immediately |
| Set to a value | The browser UI boots into a login screen; `POST /run` and `GET /run?topic=...` require a matching secret |

**How the browser UI uses the secret:**

- On load, the UI calls `GET /auth-status` to discover whether a secret is required.
- The login screen sends the typed secret to `POST /auth/verify`. On success it is stored in `sessionStorage` under `blogagent_worker_secret`. Wrong secrets do not unlock the tool.
- Every generate request sends the stored secret in the `X-BlogAgent-Secret` header.
- A `401` from `/run` clears `sessionStorage` and returns the UI to the login screen.

**How to pass the secret to the API directly:**

- Header: `X-BlogAgent-Secret: your-secret` (preferred — used by the browser UI)
- JSON body field: `worker_secret` (POST only)
- Query param: `worker_secret=your-secret` (GET only)

Comparison is constant-time (`secrets.compare_digest`). If missing or wrong, the endpoint returns `401 {"detail": "Invalid or missing worker secret"}`.

**Always public regardless of secret:** `GET /`, `GET /app`, `GET /info`, `GET /health`, `GET /auth-status`.

This is lightweight demo protection, not production auth. It has no sessions, no accounts,
no cookies, no OAuth, and no rate limiting. `sessionStorage` is browser-readable.

---

## How to request a blog post

### Via the browser UI

1. Open `/` (or `/app`) in a browser
2. If a worker secret is configured, enter it and click **Login** (otherwise you are taken straight to the tool)
3. Enter a topic
4. Click **Generate Blog Post**
5. Use **Copy article markdown**, **Download .md**, or **Download full JSON**

### Via curl

```bash
# Without secret
curl -X POST https://YOUR-VERCEL-URL.vercel.app/run \
  -H "Content-Type: application/json" \
  -d '{"topic":"Why elephants are the heaviest land animals"}'

# With secret
curl -X POST https://YOUR-VERCEL-URL.vercel.app/run \
  -H "Content-Type: application/json" \
  -H "X-BlogAgent-Secret: your-secret" \
  -d '{"topic":"Why elephants are the heaviest land animals"}'
```

---

## Skills

BlogAgent ships three Claude Code skills under `.claude/skills/`:

| Skill | Purpose |
|---|---|
| `skill-creator` | Sourced from [anthropics/skills](https://github.com/anthropics/skills). Teaches Claude Code how to create, test, and iterate on project skills. |
| `blog-post-seo-writing` | Defines how BlogAgent should structure SEO-ready article outputs: title, slug, meta description, heading rules, keyword density, and publish-readiness checklist. |
| `blog-output-evaluator` | Defines a 9-dimension rubric for judging BlogAgent article quality. Produces a structured score and blocking issue list. |

Skills are **scaffolding for Claude Code development workflows** — they do not automatically
change runtime pipeline behavior. Claude Code reads them during development to apply
consistent editorial standards and evaluation criteria when reviewing or improving BlogAgent outputs.

---

## Deployment

### Streamlit UI (local / demo)

The Streamlit UI is for **local use and demos only**. Run it with:

```bash
uv run streamlit run app/ui/streamlit_app.py
```

It is **not** the Vercel deployment target.

### Vercel API (mock-safe serverless scaffold)

BlogAgent ships a minimal FastAPI app under `api/index.py` for Vercel serverless deployment.

- Defaults to **mock mode** — no environment variables required.
- Does not publish externally.
- Does not return raw scraped webpage content.
- Publishing requests are blocked by the pipeline guardrail.

**Deploy to Vercel:**

```bash
vercel deploy
```

No environment variables are required for mock mode. The API is safe to deploy and test
without any API keys.

**Required Vercel env vars for mock mode:** none.

**Optional live provider env vars (cost-bearing):**

| Variable | Purpose |
|---|---|
| `BLOGAGENT_SEARCH_PROVIDER=tavily` | Use real Tavily search |
| `TAVILY_API_KEY` | Required for Tavily |
| `BLOGAGENT_LLM_PROVIDER=anthropic` or `openai` | Use real LLM |
| `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` | Required for chosen provider |
| `BLOGAGENT_USE_LLM_EDITOR=true` | Enable LLM for Editor Agent |
| `BLOGAGENT_USE_LLM_FACTCHECK=true` | Enable LLM for Fact-Check Evaluator |
| `BLOGAGENT_USE_LLM_CITATION_JUDGE=true` | Enable semantic per-claim citation verification |

**Browser tests (open these URLs directly):**

```
/
/app
/info
/health
/run
/run?topic=Why%20elephants%20are%20the%20heaviest%20land%20animals
```

- `/` — browser UI for generating blog posts (HTML, no framework) — **main app URL**
- `/app` — alias for `/`
- `/info` — returns service info and available endpoints as JSON
- `/health` — returns `{"status":"ok",...}`
- `/run` — returns usage instructions with example GET and POST
- `/run?topic=...` — runs the full BlogAgent pipeline and returns the compact response

**Terminal POST test:**

```bash
curl -X POST https://YOUR-VERCEL-URL.vercel.app/run \
  -H "Content-Type: application/json" \
  -d '{"topic":"Why elephants are the heaviest land animals"}'
```

**Example local API call (mock mode):**

```bash
# Start the API locally with uvicorn
uvicorn api.index:app --port 8000

# GET routes (browser-friendly)
curl http://localhost:8000/
curl http://localhost:8000/run
curl "http://localhost:8000/run?topic=Why%20elephants%20are%20the%20heaviest%20land%20animals"

# POST route
curl -X POST http://localhost:8000/run \
  -H "Content-Type: application/json" \
  -d '{"topic":"Why elephants are the heaviest land animals"}'
```

---

## Current Limitations

The **mock LLM provider is the default** — all LLM steps return deterministic output without
any API calls. This is intentional and ensures tests are always safe to run.

Real LLM calls are opt-in via `BLOGAGENT_USE_LLM_EDITOR=true` and/or
`BLOGAGENT_USE_LLM_FACTCHECK=true`, combined with `BLOGAGENT_LLM_PROVIDER=anthropic`
or `BLOGAGENT_LLM_PROVIDER=openai`.

Fact-checking is always bounded by the evidence actually in the evidence table — the
evaluator does not invent sources or accept claims without grounding.

Citation matching is deterministic and heuristic (no-sources → unsupported;
mock-only sources → partially_supported; real positive-score source → supported).
Semantic claim-to-source matching is not implemented unless LLM fact-checking is enabled.

See [docs/limitations.md](docs/limitations.md) for the complete list.

---

## Project Structure

```
blogagent/
  llm/        LLM client layer (provider selection, schemas, mock fallback)
  agents/     Editor Agent and Fact-Check Evaluator (mock default; LLM-gated)
  tools/      Tool implementations + deterministic validators
  workflow/   State models, pipeline nodes, graph runner
  evals/      Eval cases, runner, and graders

app/ui/       Streamlit UI

tests/        Pytest test suite
docs/         Architecture, eval plan, limitations
examples/     Sample outputs and run traces
```
