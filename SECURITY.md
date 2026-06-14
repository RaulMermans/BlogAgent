# Security Policy

## Reporting a Vulnerability

If you discover a security issue in BlogAgent, please open a private report via
GitHub's [Security Advisories](../../security/advisories) for this repository
rather than filing a public issue. Include:

- a description of the issue and its impact
- steps to reproduce
- the affected file(s) or endpoint(s)

We aim to acknowledge reports within a few days.

## Secrets and Configuration

BlogAgent reads all credentials from environment variables — never from
source files:

- `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY` — LLM providers
- `TAVILY_API_KEY` — search provider
- `BLOGAGENT_WORKER_SECRET` — optional shared secret for `/run` endpoints
- `AGENTPULSE_INGEST_KEY` — optional telemetry ingest key

`.env.example` lists every supported variable with a placeholder value.
Copy it to `.env` for local development; `.env` (and any `.env.*` variant
other than `.env.example`) is gitignored and must never be committed.

If a key is ever committed or leaked, rotate it immediately at the provider
and update your local/deployment environment — do not rely on removing it
from git history alone, since the old value must be treated as compromised.

## Default-Safe Behavior

- The default LLM provider is `mock` and the default search provider is
  `mock` — no API calls and no API keys are required to run the app or test
  suite.
- Real LLM calls require explicitly setting `BLOGAGENT_LLM_PROVIDER` to a
  live provider **and** opting in via `BLOGAGENT_USE_LLM_EDITOR`,
  `BLOGAGENT_USE_LLM_FACTCHECK`, and/or `BLOGAGENT_USE_LLM_CITATION_JUDGE`.
- BlogAgent never publishes, posts, emails, schedules, or otherwise modifies
  external systems. Any request containing publishing/posting/sending/
  scheduling intent is blocked before the article workflow runs (see
  `check_external_effects` in `CLAUDE.md`).

## Client-Side Exposure

No API keys are read by or exposed to client-side/browser code. All
provider calls happen server-side. The browser UI (`/app`) only ever
receives the final article package and run metadata — never raw
credentials.
