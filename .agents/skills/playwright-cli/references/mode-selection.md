# Mode Selection

Use the lightest tool that still gives deterministic evidence.

## Prefer MCP browser tools

Use MCP when the task is primarily exploratory:

- inspect a live page
- follow a long interactive flow
- keep authenticated browser state open across multiple turns
- visually debug layout, hover, focus, drag, or animation issues
- ask the user for visual feedback on the current page state

Do not treat an MCP-only walkthrough as the final regression gate when the repo already expects Playwright browser tests.

## Prefer Playwright CLI

Use Playwright CLI when the task needs shell-driven browser automation without committing a new spec yet:

- reproduce a bug quickly from the terminal
- save snapshots, screenshots, traces, or videos
- inspect console, requests, cookies, localStorage, or sessionStorage
- attach to or reopen a persistent browser profile
- keep the workflow scriptable and reproducible

## Prefer repo-local `npx playwright test`

Use repo-local Playwright specs for deterministic validation:

- test generation or test repair
- E2E regression coverage
- CI-style browser verification
- browser-visible acceptance criteria
- download, upload, auth, history, task-run, or progress-log workflows that already have neighboring specs

In MyAgent, this is usually the final gate for browser-visible changes.
