# Test Generation

Use this reference when creating or repairing Playwright tests from requirements, bug reports, or acceptance criteria.

## Rules

- Translate each acceptance criterion into one or more concrete assertions.
- Keep one responsibility per test unless the flow is intentionally end to end.
- Prefer robust locators already used by the repo.
- Avoid snapshot-style golden tests unless the repo already depends on them.

## Generation Flow

1. Read the existing test pattern in the repo.
2. Extract the minimum preconditions for the feature.
3. Encode the success path first.
4. Add failure-path assertions only when required.
5. Run the smallest relevant test target before broadening scope.

## Repair Flow

1. Reproduce the failure.
2. Decide whether the bug is in the app, the locator, or the test timing.
3. Fix the smallest unstable part.
4. Re-run the focused test before the broader suite.
