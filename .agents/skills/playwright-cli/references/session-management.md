# Session Management

Use this reference when browser state must persist across many actions or when validation needs isolation between flows.

## Defaults

- Reuse one session within a single story, scenario, or debug thread.
- Start a fresh session for unrelated stories to avoid hidden state coupling.
- Use named sessions when the task spans multiple commands.

## Persistent State

Use storage or profile persistence only when the task explicitly requires:

- login reuse
- multi-step stateful flows
- debugging an issue that appears only after several page transitions

Prefer explicit state save/load over implicit browser leftovers.

## Cleanup

- Close sessions after validation completes.
- Delete session data when the saved state should not leak into later work.
