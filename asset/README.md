# MyAgent Knowledge Pack Index

`asset/` stores durable project knowledge for future agent work. It is not a scratchpad for one-off debugging logs.

## Current Knowledge Packs

- `asset/deepagents_platform_knowledge_pack.md`: 主知识包，覆盖 DeepAgents 通用 Agent 平台架构——包括 create_deep_agent 工厂、多模型 Provider（init_chat_model）、中间件栈、流式 SSE 输出、SubAgent 子智能体、Skill 加载、文件系统工具、联网搜索工具、TaskRunner 运行时、API 路由、前端 SSE 适配、安全边界、测试布局及已知坑点。
- `asset/bid_analysis_workflow_knowledge_pack.md`: 招投标分析工作流指导，覆盖 PDF 招投标对比的业务规则、输入输出、边界条件和回归风险。
- `asset/tender_workflow_breakdown.md`: 招标工作流分解，按阶段拆解招标分析的完整流程。

## Archived Knowledge Packs

- `asset/task_workspace_runtime_knowledge_pack.md`: 已被 `deepagents_platform_knowledge_pack.md` 完整替代，仅保留作为历史参考，不再主动维护。

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

- `asset/multi_user_knowledge_pack.md` for multi-user session management, user authentication, and per-user task isolation when the platform evolves beyond single-user local mode.
