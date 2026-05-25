# Tracing

Use this reference when a browser flow is flaky, timing-sensitive, or difficult to debug from screenshots alone.

## When to Trace

- intermittent UI failures
- race conditions
- unexpected navigation or state resets
- console or network symptoms that need timeline context

## Workflow

1. Start tracing before the suspect interaction.
2. Perform the smallest flow that reproduces the issue.
3. Stop tracing as soon as enough evidence is captured.
4. Save screenshots alongside traces when they help explain the visible state.

Do not enable tracing for every run by default; keep it targeted.
