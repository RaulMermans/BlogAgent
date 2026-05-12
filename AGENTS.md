# BlogAgent — Implementation Rules

These rules apply to all contributors and AI agents working in this repository.

---

## Workflow

- Use deterministic code for: pipeline order, state transitions, schemas, validation, limits.
- Use LLMs for: research planning, synthesis, drafting, judgment, evaluation, revision.
- Do not add agents, tools, or orchestration layers unless a measured failure requires them.
- Evidence first, article second. The draft must never precede the evidence table.

---

## Factuality

- Never fabricate URLs, citations, statistics, or quotes.
- Unsupported high-importance claims block finalization and must be revised or removed.
- If sources conflict, state the conflict in the article — do not silently pick one side.
- The final `ArticlePackage` must include: article markdown, source list, fact-check report, claim support statuses, and revision summary.

---

## External Side Effects

- Do not publish to any CMS, social platform, or external system.
- Do not send emails or schedule posts.
- Do not delete or overwrite user data.
- Any future publishing tool must require explicit user confirmation before execution.

---

## Tools

Every tool must have:
- A clear, narrow purpose
- A typed `Input` Pydantic model
- A typed `Output` Pydantic model
- Structured JSON output
- A declared permission class (`read_only`, `write_draft`, `external_side_effect`, `destructive`)
- Tests

All MVP tools are `read_only` except local draft/artifact creation.

---

## Tests

- Add or update tests when changing: workflow steps, tools, schemas, validators, or evaluator behavior.
- Run the test suite before claiming a change is complete.
- Do not claim tests passed without running them.
- Do not delete test cases to make the suite pass.

---

## Architecture Changes

Before adding anything new, ask:
- Does this need to be an agent, or can it be code?
- Does this need to be a new tool, or can an existing tool be improved?
- Does this need memory, or is it just runtime state?
- Does this need a skill, or is it one-off logic?
- Does this need enforcement in settings/hooks/tests instead of a written instruction?
