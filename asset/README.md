# MyAgent Knowledge Pack Index

`asset/` stores durable project knowledge for future agent work. It is not a scratchpad for one-off debugging logs.

## Current Knowledge Packs

- `asset/frontend_task_workspace_knowledge_pack.md`: frontend chat workspace layout, task creation, file upload, message submission, polling, logs, and artifact opening.
- `asset/backend_task_runtime_knowledge_pack.md`: backend task-as-conversation APIs, run lifecycle, event logs, versioned artifacts, and local storage boundaries.
- `asset/model_provider_security_knowledge_pack.md`: model-provider secrets, environment variables, access tokens, CORS/local-first security, upload limits, and JSON limits.

## Registration Rules

- One shared rule has one main package. Other packages should reference it instead of duplicating the same boundary.
- Packages must only reference current code paths, test paths, commands, and directories.
- Do not include customer source text, secrets, tokens, private local paths, or other sensitive data.
- Do not preserve patch timelines, deleted filenames, or temporary script paths as long-term knowledge.
- If a new package fully absorbs an old package, delete the old package and update this index in the same change.
- Do not keep a separate package for single-machine development walkthroughs. Keep concise reusable script cautions in `AGENTS.md` and operational steps in `README.md`.

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

- `asset/bid_analysis_workflow_knowledge_pack.md` for Markdown document classification, bid-collusion analysis categories, sub-agent assignment, evidence normalization, and report generation.
