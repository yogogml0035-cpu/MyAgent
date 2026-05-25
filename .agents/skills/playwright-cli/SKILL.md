---
name: playwright-cli
description: Browser automation with Playwright MCP for interactive page exploration, long-lived browser sessions, and UI debugging, plus Playwright CLI for repo-bound test generation, E2E validation, CI-style checks, screenshots, traces, and storage-state workflows. Use when Codex needs to navigate web apps, inspect or interact with pages, persist browser state, debug UI behavior, generate Playwright tests, or validate acceptance criteria in a real browser.
---

# Playwright Automation

Use one Playwright family workflow for all browser work in this repo.

## Decision Rule

- Use Playwright MCP when the current runtime exposes browser tools and the task is exploratory, interactive, or stateful:
  - opening a page and inspecting it
  - clicking around to understand UI behavior
  - keeping a long-lived browser session open across many actions
  - debugging page state, console output, or a flaky interaction
- Use Playwright CLI for repo-bound automation:
  - generating or updating Playwright tests
  - E2E validation tied to requirement acceptance criteria
  - CI-style repeatable verification
  - deterministic screenshots, traces, storage-state capture, and network evidence
  - spawned agents or scripts that may not have MCP tools

## Command Resolution

Resolve Playwright CLI in this order:

```bash
playwright-cli --version
npx --no-install playwright-cli --version
npx --yes @playwright/cli@latest --version
```

- If the global command exists, use `playwright-cli`.
- If only the local binary exists, use `npx playwright-cli`.
- Otherwise use `npx --yes @playwright/cli@latest ...`.

Keep the chosen command form consistent throughout the task.

## MCP Workflow

Use Playwright MCP for exploration and debugging:

1. Open or attach to the target page.
2. Inspect with page snapshots before interacting.
3. Reuse the same browser session while exploring.
4. Take screenshots only when they add evidence; use snapshots for most interaction targeting.
5. Save screenshots to the exact path the caller provides.

Prefer MCP when the user wants quick iteration, long-lived browser state, or direct interaction debugging.

## CLI Workflow

Use Playwright CLI for repeatable browser execution:

```bash
playwright-cli open https://example.com
playwright-cli snapshot
playwright-cli click e15
playwright-cli fill e21 "user@example.com"
playwright-cli screenshot --filename=page.png
playwright-cli console
playwright-cli requests
playwright-cli tracing-start
playwright-cli tracing-stop
playwright-cli close
```

Guidelines:

- Prefer named sessions for validation work, for example `-s=validator-us-002`.
- Reuse a session within one story or test flow.
- Reset state between unrelated stories unless the acceptance criteria explicitly require persistence.
- Save screenshots with explicit file names into the caller's screenshot directory.

## Repo Test Workflow

When the task is tied to code in the repository:

1. Inspect existing Playwright config, test layout, and naming patterns before adding tests.
2. Prefer extending existing suites over creating a parallel test harness.
3. Encode acceptance criteria as assertions, not only as manual steps.
4. Keep one-off exploratory validation separate from committed tests.
5. When a flow should be reproducible in CI, promote it into a Playwright test or a stable CLI script.

Read the targeted reference before deeper work:

- Playwright project layout and execution: [references/playwright-tests.md](references/playwright-tests.md)
- Generating or repairing tests: [references/test-generation.md](references/test-generation.md)
- Reusing auth/session state: [references/session-management.md](references/session-management.md)
- Cookies and storage state: [references/storage-state.md](references/storage-state.md)
- Traces and debug artifacts: [references/tracing.md](references/tracing.md)

## Validation Artifacts

When the caller provides requirement-scoped `screenshots/` or `logs/` paths:

- write screenshots exactly there
- use stable, story-scoped names
- capture evidence after major state changes and always on failure
- collect console, network, and trace evidence when acceptance depends on runtime behavior

## Quick Patterns

### Interactive review with MCP

- open the local app
- inspect with a snapshot
- interact and keep the session alive
- capture screenshots only when needed for review or evidence

### Requirement validation with CLI

```bash
playwright-cli -s=validator-us-002 open http://localhost:3000
playwright-cli -s=validator-us-002 snapshot
playwright-cli -s=validator-us-002 click e12
playwright-cli -s=validator-us-002 screenshot --filename=D:/path/to/screenshots/validator-us-002-pass-1.png
playwright-cli -s=validator-us-002 console
playwright-cli -s=validator-us-002 close
```

### Repo-bound E2E work

- inspect existing tests first
- add or repair the smallest useful Playwright test
- run the narrowest validation command first
- widen to CI-style coverage only when the narrower run passes
