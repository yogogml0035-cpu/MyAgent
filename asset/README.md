# MyAgent Knowledge Pack Index

`asset/` stores durable project knowledge for future agent work. It is not a scratchpad for one-off debugging logs.

## Current Knowledge Packs

No topic knowledge packs exist yet.

When the first stable topic boundary appears, update this index before adding the package file.

## Registration Rules

- One shared rule has one main package. Other packages should reference it instead of duplicating the same boundary.
- Packages must only reference current code paths, test paths, commands, and directories.
- Do not include customer source text, secrets, tokens, private local paths, or other sensitive data.
- Do not preserve patch timelines, deleted filenames, or temporary script paths as long-term knowledge.
- If a new package fully absorbs an old package, delete the old package and update this index in the same change.

## Required Package Sections

Each knowledge pack should include:

```markdown
# <Topic> Knowledge Pack

## Background And Scope

## Business Rules

## Input And Output Examples

## Boundary Conditions

## Known Pitfalls

## Related Code Paths

## Related Test Paths

## Verification Commands

## Regression Risks
```

## Suggested Future Routes

These filenames are suggested routes, not current packages:

- `asset/backend_task_runtime_knowledge_pack.md` for backend task APIs, state transitions, runner behavior, cancellation/interruption, event logs, artifact download, and local storage.
- `asset/bid_analysis_workflow_knowledge_pack.md` for Markdown document classification, bid-collusion analysis categories, sub-agent assignment, evidence normalization, and report generation.
- `asset/frontend_task_workspace_knowledge_pack.md` for task creation, file upload, message submission, polling, log merging, artifact URLs, and artifact opening.
- `asset/model_provider_security_knowledge_pack.md` for model providers, environment variables, access tokens, CORS, local-first security, upload limits, and JSON limits.
