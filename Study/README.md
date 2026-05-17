# MyAgent 学习目录

这个目录是给刚开始学习本项目的同学准备的。它不讲部署和安装，只讲三件事：

1. 项目的架构设计：后端、Agent 运行时、前端状态层如何协作。
2. 代码功能和业务逻辑：每个关键模块负责什么，为什么要这样拆。
3. 可验证的小练习：每章都有一个最小代码单元，你可以运行、改坏、再改回来。

## 建议学习顺序

| 顺序 | 章节 | 你会学会什么 |
| --- | --- | --- |
| 0 | [学习计划](./learning_plan.md) | 如何按阶段学习，不迷路 |
| 1 | [全局架构地图](./architecture_map.md) | 一次任务从页面到 Agent 再回页面的完整链路 |
| 2 | [术语表](./glossary.md) | 先把项目里的高频名词弄懂 |
| 3 | [01 大图景](./chapters/01_big_picture/README.md) | MyAgent 的分层和核心数据流 |
| 4 | [02 后端 API 与 Schema](./chapters/02_backend_api_schemas/README.md) | FastAPI 路由、请求模型、响应状态 |
| 5 | [03 Storage 与事件日志](./chapters/03_storage_event_log/README.md) | 为什么 Postgres 是事实来源，事件 seq 为什么重要 |
| 6 | [04 Runner 与 DeepAgents](./chapters/04_runner_deepagents/README.md) | 一次 Agent run 如何启动、流式执行、结束 |
| 7 | [05 上传资源、工具与产物](./chapters/05_uploads_tools_artifacts/README.md) | 上传文件如何变成 task-scoped resource |
| 8 | [06 流式事件与前端状态](./chapters/06_streaming_frontend_state/README.md) | SSE 事件如何变成页面日志和 AI 回复 |
| 9 | [07 前端工作区](./chapters/07_frontend_workspace/README.md) | TaskWorkspace、Hook、Composer、Conversation 的分工 |
| 10 | [08 安全、记忆与测试](./chapters/08_security_memory_testing/README.md) | 本地优先安全边界、长期记忆、测试结构 |
| 11 | [09 招投标分析工作流](./chapters/09_bid_analysis_workflow/README.md) | 招投标业务规则如何落到 Agent 平台 |
| 12 | [最终自测](./final_self_check.md) | 检查是否能从用户动作反推源码 |

维护记录见 [Study 资料审计记录](./audit_notes.md)。

## 怎么使用这些练习

每章都有一个 `mini_unit.py` 或 `mini_unit.mjs`。推荐这样学：

1. 先读本章 `README.md`。
2. 运行最小代码单元，看它输出什么。
3. 按 README 里的提示故意改坏一处逻辑。
4. 再运行，观察失败信息。
5. 对照 `answers.md`，用自己的话复述核心概念。

这些最小代码单元分两类：

- 概念验证：用很少的代码复现项目里的关键设计，例如 run_id 先由 storage 生成。
- 源码锚点验证：读取当前仓库源码，确认文档讲到的函数、字段、边界真的存在。

你也可以一次性运行所有练习：

```bash
python3 Study/run_all_mini_units.py
```

这只是学习验证，不是项目的正式测试入口。正式测试仍然看 `backend/tests/`、`frontend/tests/` 和 `frontend/e2e-playwright/`。

## 初学者读源码的节奏

不要一上来从 `backend/app/storage.py` 第一行读到最后一行。更稳的方式是按“用户动作”追：

1. 用户在哪里点击发送：`frontend/components/chat/ChatComposer.tsx`
2. 谁编排发送流程：`frontend/hooks/use-task-workspace.ts`
3. 请求发到哪里：`frontend/lib/task-api.ts`
4. 后端哪个路由接住：`backend/app/api/tasks.py`
5. 谁创建 run 和写事件：`backend/app/storage.py`
6. 谁真正跑 Agent：`backend/app/runner/core.py`
7. 前端怎样恢复进度：`backend/app/api/streaming.py`、`frontend/app/workspace-view.ts`

如果某章提到“需要结合源码进一步确认”，意思是：已有知识包或设计边界说明了方向，但当前仓库还没有完整生产实现，不能把它当作已上线功能背下来。
