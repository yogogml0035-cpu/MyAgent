# Storage State

Use this reference when acceptance criteria mention authentication, cookies, localStorage, sessionStorage, or state restoration.

## Use Cases

- save authenticated state after login
- verify tokens or session markers exist
- restore state to validate refresh or resume behavior
- clear state to reproduce first-run behavior

## Guidance

- Treat storage as evidence, not as the primary validation target.
- Validate the user-visible outcome together with the storage mutation.
- Clear state before negative-path or first-run checks when stale data could hide failures.
