# 后端风险与关注点

**分析日期：** 2026-05-25

## 技术债

### `PostgresTaskStorage` 责任过重

- 问题：同一个类负责 DDL、task lifecycle、event sequencing、upload、artifact、tool cache、agent store、context summary 和长期记忆。
- 文件：`backend/app/storage.py`。
- 影响：上传、事件、产物、记忆或 agent-store 的小改动都要编辑超大模块，回归风险高。
- 建议：按 task/event repository、upload/artifact filesystem service、agent-store repository、tool-cache repository、long-term-memory repository 拆分；保留兼容 facade。

### startup 中隐式做 schema 管理

- 问题：schema 创建和列变更嵌在 `initialize()`，没有 versioned migration。
- 影响：生产启动会隐式变更 schema，缺少 rollback、顺序、锁和 migration history。
- 建议：引入 migration 机制或 schema-version table，把 `initialize()` 收窄为启动检查。

### request/message options 接收但部分语义未完全落地

- 问题：`MessageRequest.mode`、`input_scope` 等字段可能被客户端视为有语义，但执行路径未必完整使用。
- 影响：产品语义和后续开发假设容易漂移。
- 建议：要么接入 runner 行为并补测试，要么在功能成熟前收窄 API。

### 配置解析手写且容错过宽

- 问题：`.env` loading 和环境变量解析自定义，部分无效值会 silent fallback。
- 影响：生产配置错误难诊断。
- 建议：增加 fail-fast validators 或使用 typed settings library。

### 搜索缓存、agent store、长期记忆共享 storage 路径

- 问题：cache、memory、store 通过同一 storage implementation 和 Postgres connection path。
- 影响：独立清理、观测和扩展困难。
- 建议：提取窄 repository/protocol。

## 已知问题

- memory write background task 在 shutdown 时未被集中 drain/cancel；进程退出可能让 Qdrant index 滞后，可用 `memory_admin.py rebuild-qdrant` 从 Postgres 重建。
- `workspace_root` 默认等于 `task_root`，operator 不能独立区分 session metadata 和 agent workspace。
- query-string token 支持 SSE，但 URL 可能进入浏览器历史、代理日志或 referrer；非 SSE 优先用 header token。
- 删除 task 先删数据库再 `ignore_errors=True` 删除文件，文件系统失败可能留下 orphaned task 目录。

## 安全关注

- query token 有 URL 泄露风险，应优先 header token；SSE 可考虑短期 stream token 或同源 proxy。
- 默认 loopback auth 依赖直接 client address；绑定到 LAN 或代理后必须显式配置 token 和 CORS。
- `MYAGENT_SEARXNG_URL` 是可配置外部 URL，应限制 scheme/host 或把远程搜索作为显式生产设置。
- secret scanner 未覆盖所有输出通道；final answer、event payload、artifact、search result 是否需要统一输出 gate 需要产品决策。
- `MYAGENT_SKILLS_DIRS` 可挂载任意目录为只读技能源，只适合 operator 完全控制环境变量的部署。

## 性能瓶颈

- SSE 每个连接 0.5 秒轮询 Postgres；后续可引入 LISTEN/NOTIFY 或 active-run in-process queue。
- task list 通过完整 `TaskState` 组装 summary，任务多时成本高；可改为聚合查询。
- DOCX/XLSX 资源解析同步执行，缺少页数、sheet size、parse time 和 CPU budget。
- agent store filtered search 在 Python 内存过滤，JSONB 查询可下推 SQL。
- long-term memory rebuild 逐条 embedding/upsert，缺少 batch 和进度反馈。

## 脆弱区域

- Runner 状态分裂在 Postgres 和进程内 `_active_runs`；变更 runner lifecycle 时必须覆盖 startup interruption、cancel、stale active-run id。
- Event seq 和 cursor 是 UI 正确性的核心；`after_id` miss 必须 fail open，不能返回空导致事件丢失。
- Artifact name/path 同时涉及 latest mirror 和 run-scoped 目录；所有路径必须使用 `normalize_artifact_name()` 和 `validate_run_id()`。
- DeepAgents/LangGraph/LangChain stream shape 可能随依赖升级变化；升级前保存 fixtures 并跑 streaming tests 和 SSE E2E。
- 长期记忆有 Postgres canonical rows 和 Qdrant index 两套失败模式；Postgres 是权威，Qdrant 要可重建。

## 扩展限制

- 当前单进程 task execution 无法水平扩展；启用多 worker 前需要 durable job queue、task lease、worker heartbeat、distributed cancellation 和 event publishing。
- storage 方法每次新建 psycopg connection；高并发 SSE 和 task list 可能耗尽连接。
- 上传大小限制不能代表解析复杂度限制；Office 文件需要 parse budget、缓存和更安全的 read mode。
- task、message、event、artifact、upload、tool cache、memory 没有完整 retention 策略。

## 依赖风险

- `langgraph-checkpoint` 使用 Git pin，复现依赖 Git 可用和 commit 可获取。
- DeepAgents/LangGraph/LangChain stream contract 变化会影响 `stream_agent()`、reasoning delta、tool event 和 final answer extraction。
- 记忆服务在生产启动中关键，Qdrant/DashScope 不可用会导致启动失败。
- `python-docx` 和 `openpyxl` 解析用户上传文档，需要持续更新并加 malformed-file/资源耗尽测试。

## 缺失能力

- 没有专用 migration system。
- 没有 connection pooling 或数据库健康指标。
- 没有统一输出脱敏 gate。
- 没有 durable worker queue。
- 没有 task/artifact retention 管理。

## 测试缺口

- 真实 Postgres 路径多为 env-gated integration，CI 未配置时会漏掉生产 storage 回归。
- Qdrant/DashScope 网络错误、维度漂移、部分写失败和 recall threshold 覆盖不足。
- SearXNG invalid URL、慢响应、redirect、大 payload、预算耗尽和 refresh cache 行为仍需要继续扩展覆盖；当前已有引擎选择、代理重试和预算相关单测。
- Office 文档安全解析缺少 malformed/zip-bomb-like/huge sheet/formula/external link 测试。
- auth 缺少非 loopback、proxy、LAN origin/CORS 场景。
- startup/shutdown 对 active runs、memory write、文件写入中断的覆盖有限。

---

*风险审计：2026-05-25*
