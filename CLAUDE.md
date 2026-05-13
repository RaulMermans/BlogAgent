# BlogAgent — Project Constitution

BlogAgent is a source-grounded editorial agent that turns a user topic into a researched, fact-checked, SEO-ready blog post.

This is not a generic AI blog generator. It is an agentic editorial workflow with:

- web research
- source extraction
- source scoring
- evidence tables
- claim extraction
- citation matching
- evaluator-based revision
- final article packaging

Primary goal: produce trustworthy blog drafts with visible research traces and claim-level support.

---

## Core Principle

Keep the architecture boring. Make the evidence layer impressive.

Use deterministic code for:

- workflow order
- state transitions
- schemas
- validation
- search limits
- revision limits
- persistence
- tests
- evals
- guardrails

Use LLMs for:

- research planning
- synthesis
- outline generation
- drafting
- judgment
- revision
- evaluator feedback

Do not add agents, tools, memory, or orchestration layers unless they solve a measured failure.

---

## MVP Architecture

The MVP is a hybrid deterministic workflow with two model roles.

Agents:

1. Editor Agent
2. Fact-Check Evaluator

Tools:

1. web_search
2. webpage_extract
3. source_score
4. claim_extractor
5. citation_matcher
6. blog_package_validator

Default workflow:

```text
User Topic
→ Intake Parser
→ check_external_effects (guardrail)
→ Editor Agent research plan
→ web_search
→ webpage_extract
→ source_score
→ Evidence Table Builder
→ Editor Agent outline
→ Editor Agent draft
→ Fact-Check Evaluator
→ claim_extractor
→ citation_matcher
→ blog_package_validator
→ Editor Agent revision if needed
→ Final Article Package
```

Do not create extra agents unless there is a clear repeated failure, such as weak research, poor citation matching, poor SEO metadata, or bad style consistency.

---

## **Non-Negotiable Factuality Rules**

IMPORTANT: Never fabricate URLs, citations, statistics, quotes, source titles, file paths, API behavior, tool results, or test results.

IMPORTANT: Unsupported factual claims must be removed, rewritten, or marked uncertain.

IMPORTANT: Numerical claims require source support.

IMPORTANT: If sources conflict, state the conflict clearly instead of silently choosing one.

IMPORTANT: The final article package must include:

* article markdown
* source list
* fact-check report
* claim support statuses
* revision summary
* title, slug, meta_description, seo_keywords

No final article is complete without source grounding.

---

## **External Side Effects**

The MVP must not publish externally.

Forbidden without explicit user approval:

* publishing to CMS
* posting to social media
* sending emails
* scheduling posts
* modifying external systems
* deleting user data
* overwriting remote content

If a request contains publishing/posting/sending/scheduling keywords, the pipeline sets `blocked=True` and returns immediately without running the article workflow.

If a future publishing tool is added, it must require explicit user confirmation.

---

## **Development Rules**

Before making changes:

1. Inspect existing files before editing.
2. Identify the smallest safe change.
3. Preserve existing behavior unless the task explicitly asks for a change.
4. Prefer deterministic code over prompting for validation, formatting, limits, and schema checks.
5. Add or update tests when changing workflow, tools, schemas, or evaluator behavior.
6. Run relevant verification commands before claiming completion.
7. If a command fails, report the failure honestly and do not claim success.

For architecture changes, ask:

* Does this need to be an agent, or can it be code?
* Does this need to be a new tool, or can an existing tool be improved?
* Does this need memory, or is it just runtime state?
* Does this need a skill, or is it one-off logic?
* Does this need enforcement in settings/hooks/tests instead of a written instruction?

---

## **Source-Grounding Rules**

The article writer must not draft first and "find sources later."

Correct order:

research questions
→ source search
→ source extraction
→ source scoring
→ evidence table
→ outline
→ draft
→ claim extraction
→ citation matching
→ revision
→ final package

Evidence table items should include:

* fact
* source URL
* source title
* publisher/domain
* confidence
* used_for

Citation matching should classify claims as:

* supported
* partially_supported
* unsupported

Unsupported high-importance claims block finalization until revised.

---

## **Tool Design Rules**

All tools must have:

* clear name
* narrow purpose
* typed input schema
* typed output schema
* structured JSON output
* actionable error messages
* permission class
* tests

Preferred permission classes:

* read_only
* write_draft
* external_side_effect
* destructive

For MVP, tools should be read-only except local draft/artifact creation.

Tool outputs should be useful to an agent. Avoid raw blobs when a structured summary is enough.

---

## **State and Memory Policy**

Separate state, memory, artifacts, and logs.

Runtime state:

* topic
* research questions
* search results
* selected sources
* source scores
* evidence table
* outline
* draft
* claims
* citation matches
* fact-check report
* final article package
* blocked / block_reason / requires_approval

Persist:

* final article package
* selected source URLs
* source scores
* evidence table
* fact-check report
* run metadata
* evaluator outcome

Do not persist by default:

* raw scraped full webpages
* secrets
* API keys
* private user data
* unsupported claims
* temporary assumptions
* one-off user preferences

Long-term memory should contain only durable, reusable, project-specific lessons.

---

## **Compounding Memory Protocol**

This project should improve after failures.

After tests, review, or user correction, decide whether a lesson should become durable project memory.

Store a lesson only if it is:

* reusable
* project-specific
* likely to recur
* testable or verifiable
* not a temporary preference
* not sensitive
* not speculation

Placement rules:

* Universal project rule → `CLAUDE.md`
* Topic-specific implementation rule → `.claude/rules/*.md`
* Repeatable workflow → `.claude/skills/*/SKILL.md`
* Specialized reviewer/worker role → `.claude/agents/*.md`
* Long reference material → `docs/*.md`
* Hard enforcement → settings, hooks, tests, CI
* Regression behavior → tests/ or evals/

Do not dump every correction into `CLAUDE.md`.

When proposing a memory update, use this format:

## Proposed Memory Update

Failure observed:

- ...

Reusable lesson:

- ...

Recommended storage location:

- ...

Why this belongs there:

- ...

Verification:

- ...

If the lesson is not reusable, do not store it.

---

## **Evaluation Rules**

Every major workflow change should preserve or improve eval performance.

Initial eval suite should include:

* simple factual topic
* scientific explainer
* historical topic
* contradictory data topic
* current/recent topic
* weak-evidence topic
* no-research-needed topic
* unsafe publishing request

Track:

* schema validity
* fake URL rate
* minimum source count
* unsupported key claims
* citation match accuracy
* revision improvement
* latency
* cost per run, if available

Target standards:

* fake URL rate: 0%
* final package schema validity: 100%
* unsupported high-importance claims: 0 in final output
* at least 3 credible sources for factual research topics

---

## **Anti-Patterns to Avoid**

Avoid:

* multi-agent theater
* one giant prompt
* adding tools before defining schemas
* drafting before evidence exists
* "trust me" citations
* storing every correction forever
* using `CLAUDE.md` for hard enforcement
* claiming tests passed without running them
* using LLMs for deterministic validation that code can do
* adding CMS publishing before approval gates exist
* expanding architecture before the trust layer works

---

## **Suggested Commands**

```bash
# install dependencies
uv sync

# run tests
uv run pytest

# lint / format
uv run ruff check .
uv run ruff format .

# run app
uv run streamlit run app/ui/streamlit_app.py

# run evals
uv run python -m blogagent.evals.runner
```

Never invent successful command output. If a command was not run, say it was not run.

---

## **Final Reminders**

IMPORTANT: Evidence first, article second.

IMPORTANT: Do not fabricate sources, claims, command results, or test outcomes.

IMPORTANT: Keep `CLAUDE.md` concise. Move detail into rules, skills, docs, tests, hooks, or settings.

IMPORTANT: Each line in this file should pass the test: "If this line were removed, would Claude plausibly make a real project mistake?"
