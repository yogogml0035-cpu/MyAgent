# Playwright Tests

Use this reference when the repo already contains Playwright tests or when the task should become a repeatable E2E check.

## Workflow

1. Find existing config, fixtures, helpers, and test directories first.
2. Mirror the local naming, import style, and locator conventions.
3. Prefer small test additions close to the affected feature.
4. Keep setup in fixtures or helpers; keep the test body focused on assertions.

## Execution

- Start with the narrowest target: one file, one test, or one project.
- Use headed or trace-enabled runs only when debugging requires it.
- If the task is purely exploratory, do not commit a speculative test suite.

## Assertions

- Assert user-visible outcomes.
- Assert URL, console, storage, or network behavior only when required by acceptance criteria.
- Avoid weak assertions such as "page loads" when the feature requires a concrete state change.
