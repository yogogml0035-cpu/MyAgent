# MyAgent Knowledge Pack Index

`asset/` stores durable project knowledge for future agent work. It is not a scratchpad for one-off debugging logs.

## Current Knowledge Packs

- `asset/task_workspace_runtime_knowledge_pack.md`: the single main package for backend task runtime, DeepAgent multi-agent profile routing, frontend task workspace, user-facing live log projection, streamed `AI回复` result panels, frontend architecture boundaries, frontend visual-token boundaries, text-only empty-state wordmark, row-level robot avatar treatment, composer/message-card alignment, clipboard feedback, model-provider security, upload limits, local-first access boundaries, artifact handling, and test layout.

## Registration Rules

- One shared rule has one main package. Other packages should reference it instead of duplicating the same boundary.
- Packages must only reference current code paths, test paths, commands, and directories.
- Do not include customer source text, secrets, tokens, private local paths, or other sensitive data.
- Do not preserve patch timelines, deleted filenames, or temporary script paths as long-term knowledge.
- If a new package fully absorbs an old package, delete the old package and update this index in the same change.
- Do not keep a separate package for single-machine development walkthroughs. Keep concise reusable script cautions in `AGENTS.md` and operational steps in `README.md`.
- Test-path changes must update this index, the relevant knowledge package, and `AGENTS.md` in the same change.

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
