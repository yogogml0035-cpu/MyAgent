<!-- refreshed: 2026-05-24 -->
# 后端架构

**分析日期：** 2026-05-24

## 系统总览

`backend/` 是 MyAgent 的任务生命周期和运行时权威边界。它用 FastAPI 提供 HTTP/SSE API，用 Postgres 保存任务、运行、消息、事件和长期记忆元数据，用本地文件系统保存上传与产物，并在进程内通过 DeepAgents/LangGraph 执行 agent run。

```text
FastAPI app (`backend/app/main.py`)
  -> API routers (`backend/app/api/`)
  -> TaskRunner (`backend/app/runner/core.py`)
  -> Agent factory / tools / resources (`backend/app/agent/`, `backend/app/tools/`, `backend/app/execution/`)
  -> Storage / memory / stream adapters (`backend/app/storage.py`, `backend/app/memory.py`, `backend/app/streaming/`)
  -> Postgres / local files / DeepSeek / DashScope embeddings / Qdrant / SearXNG
```

## 组件职责

| 组件 | 职责 | 入口 |
| --- | --- | --- |
| 应用组装 | 创建 FastAPI app，加载 settings，接入 storage、memory、runner、auth、CORS 和请求体限制 | `backend/app/main.py` |
| 任务 API | 创建/读取/重命名/删除 task，发送 message，创建 run，校验模型和技能，取消运行，读取事件 | `backend/app/api/tasks.py` |
| 文件 API | 在 task 非运行时接受上传，委托 storage 做文件名、格式、大小、JSON 和重复校验 | `backend/app/api/files.py` |
| 产物 API | 通过 storage resolver 提供 latest 或 run-scoped artifact 下载 | `backend/app/api/artifacts.py` |
| SSE API | 轮询持久化事件并输出 Server-Sent Events | `backend/app/api/streaming.py` |
| 模型 API | 返回浏览器安全的模型元数据和 availability 标记 | `backend/app/api/models.py` |
| 技能 API | 从 `backend/skills/*/SKILL.md` 返回浏览器安全的技能名称和描述 | `backend/app/api/skills.py` |
| Runner | 构建 agent，注入上下文/记忆/资源 manifest，流式转换事件，更新终态并调度记忆写入 | `backend/app/runner/core.py` |
| Agent factory | 构建 DeepAgents/LangGraph graph，挂载 workspace、只读 skill backend、tools、store 和 scratch state | `backend/app/agent/factory.py` |
| 平台工具 | 聚合上传资源工具和 SearXNG 搜索工具 | `backend/app/tools/registry.py`, `backend/app/execution/resources.py` |
| Storage | 持久化任务、run、消息、事件、agent store、工具缓存、长期记忆、上传和产物 | `backend/app/storage.py` |
| Memory | 用 DashScope-compatible embeddings 与 Qdrant 做长期记忆 recall/index，Postgres 保存 canonical rows | `backend/app/memory.py` |
| 上下文 | 从 Postgres message、summary 和新鲜 tool cache 构建同会话上下文 | `backend/app/conversation_context.py` |
| Streaming | 把 LangGraph v2 chunks 规范化为平台事件并写入事件日志 | `backend/app/streaming/` |

## 分层结构

### HTTP/API 层

- 位置：`backend/app/api/`
- 负责 REST/SSE endpoint、请求状态校验、HTTP 错误映射和 Pydantic response model。
- 路由保持薄层，依赖 `request.app.state` 获取 storage、runner、settings 等服务。

### 组装与运行时层

- 位置：`backend/app/main.py`
- `create_app(...)` 是依赖注入入口，测试可以传入 fake storage、memory service 或 title generator。
- app lifespan 负责初始化 storage/memory/agent store，并在启动时中断陈旧 running task。

### Runner 编排层

- 位置：`backend/app/runner/core.py`
- `TaskRunner` 管理 active run、取消、超时、流事件落库、终态事件、final answer 和 completed-run memory write。
- 当前 active run map 是进程内状态，不能绕过单 worker 保护。

### Agent 构建层

- 位置：`backend/app/agent/`
- 把 settings 转成 DeepAgents graph，接入模型、工具、workspace backend、只读 skills backend 和可选 LangGraph store。
- `/skills/` 是只读虚拟挂载；task 文件写入仍限制在当前 task workspace。

### 工具与资源层

- 位置：`backend/app/tools/`, `backend/app/execution/`
- 上传文件不是自动上下文，只通过 `list_uploaded_resources`、`inspect_resource`、`read_resource_text`、`read_resource_table` 暴露。
- SearXNG 搜索工具只通过 settings 中的 URL 注册和调用。

### 持久化层

- 位置：`backend/app/storage.py`
- Postgres 是任务、run、message、event、agent store、tool cache 和 long-term memory metadata 的权威来源。
- 上传和产物文件在本地 task 根目录下按 task/run 归档，所有路径都必须经过 storage 或 resource adapter 校验。

### 记忆与上下文层

- 位置：`backend/app/conversation_context.py`, `backend/app/memory.py`, `backend/app/security/scanner.py`
- 普通上下文只消费 canonical messages、summary 和受控 cache；不能把 reasoning/tool raw diagnostics 注入普通历史。
- 长期记忆写入以 Postgres canonical row 为准，Qdrant 是可重建的向量索引。

### 流事件层

- 位置：`backend/app/streaming/`
- `v2_adapter.py` 兼容 LangGraph v2 dict chunk 和旧 tuple chunk。
- `event_converter.py` 生成 `EventRecord`，SSE endpoint 只投影已持久化事件。

## 关键数据流

### 任务运行路径

1. 浏览器调用 `POST /api/tasks` 或 `POST /api/tasks/{task_id}/messages`。
2. 任务路由校验模型 availability、项目技能和 task 状态。
3. `PostgresTaskStorage.start_run(...)` 把 task 置为 `running`，创建 run row 并写入用户消息。
4. 路由调用 `TaskRunner.start_background(...)`。
5. Runner 创建 task workspace，构建工具和 agent，注入同会话上下文、长期记忆和资源 manifest。
6. `stream_agent(...)` 读取 LangGraph v2 stream modes 并输出规范化事件。
7. `convert_stream_event(...)` 转成 `EventRecord`，storage 按 task seq 落库。
8. Runner 提取最终答案，更新 task 终态，追加 `final_answer` 和终端事件，并异步调度记忆写入。
9. 取消请求走快速返回路径：任务 API 调用 runner 的 no-wait cancel request 后立即把当前 run 标记为 `cancelled` 并追加 run-scoped `task_cancelled` event，后台 asyncio task 再异步收敛。

### SSE 路径

1. 浏览器打开 `GET /api/tasks/{task_id}/stream`。
2. 后端检查 task 存在并返回 `text/event-stream`。
3. `_event_stream(...)` 使用 `storage.read_events(... after_id=last_event_id)` 轮询并输出完整事件 JSON。
4. runner 结束后，SSE 先 drain 剩余事件，再发送 done 并关闭。

### 上传与资源工具路径

1. 浏览器用 `POST /api/tasks/{task_id}/files` 上传。
2. API 拒绝 missing task 和 running task。
3. Storage 校验文件名、扩展名、重复、大小、JSON 内容和请求限制，写入 `<task>/uploads/`。
4. Storage 追加 `file_uploaded` 事件和稳定 `resource_ref`。
5. 下一轮 run 中，Runner 注入资源 manifest，agent 通过资源工具按需读取。
6. Word/docx 交付生成走 `create_word_document`，该工具接收 Markdown/纯文本并转换为 Word 原生标题、列表和表格，然后直接生成并登记当前 run artifact；当前 backend 不提供 shell/python/execute 命令执行能力，不应通过 `bash`、`execute` 或 `task` 子代理生成简单 Word 文件。

### 产物下载路径

1. 产物元数据由 storage 归入 task state。
2. latest artifact 使用 `/api/tasks/{task_id}/artifacts/{artifact_name}`。
3. run-scoped artifact 使用 `/api/tasks/{task_id}/runs/{run_id}/artifacts/{artifact_name}`。
4. Storage 校验 artifact name、run id、run artifact membership 和路径边界。

### 模型和技能发现路径

- `/api/models` 只返回 `MODEL_REGISTRY` 中浏览器安全的 ID 和 availability。
- `/api/skills` 只读取仓库内 `backend/skills` 的 name/description，不暴露技能正文和本地路径。
- message payload 可以带 selected skill names；后端校验后把可见 `[$skill]` 引用加入实际 message。

## 关键抽象

- `Settings`：不可变运行配置，集中在 `backend/app/config.py`。
- Pydantic schemas：浏览器/API 合同在 `backend/app/schemas.py`。
- `TaskRunner`：单次 agent run 的编排边界。
- `PostgresTaskStorage`：持久状态和本地文件安全边界。
- `EventRecord`：事件日志、SSE 和前端 live metadata 的共享 DTO。
- Resource refs：上传和产物用 `myagent://...` 稳定身份，不应发明临时 URL/ID。
- Project skills：`backend/skills/<skill>/SKILL.md`，frontmatter 只需 name/description。
- `PostgresAgentStore`：LangGraph `BaseStore` 的 Postgres 适配层。

## 入口

- ASGI app：`backend/app/main.py`，本地命令 `uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8001`。
- 可测试 app factory：`create_app(...)`。
- 任务 API：`backend/app/api/tasks.py`。
- SSE API：`backend/app/api/streaming.py`。
- 文件上传 API：`backend/app/api/files.py`。
- 产物下载 API：`backend/app/api/artifacts.py`。
- 记忆管理 CLI：`backend/app/memory_admin.py`。

## 架构约束

- 当前 runner 是进程内 active-run 模型；`backend/app/config.py` 会拒绝多 worker 环境变量。
- SSE 是持久化事件投影，不是原始 LangGraph stream；前端恢复依赖有序事件日志。
- 上传、产物、workspace 和 run id 必须经过 storage/resource adapter 的路径校验。
- `backend/.env` 可以存在但不能被文档、测试、截图或知识包读取/引用具体值；配置事实使用 `.env.example` 和代码。
- 生产启动需要 Postgres，记忆能力需要 Qdrant 和 DashScope-compatible embedding 配置。
- API 访问默认只允许 loopback；对外暴露必须配置 token 与 CORS。

## 反模式

- 不要在 router 中直接实现存储变更、模型调用或 agent 执行；应委托 storage、runner 或服务层。
- 不要在 API route 或工具里手写上传/产物路径解析；用 storage resolver 和 resource adapter。
- 不要把原始 LangGraph chunks 直接推给浏览器；必须规范化、落库，再由 SSE 投影。
- 不要把 worker 数调大来“扩容”当前 runner；需要先设计外部队列、租约、心跳和跨进程事件发布。
- 不要假设上传文件内容已在 chat context 中；agent 必须通过资源工具读取。
- 不要让模型调用 `bash`、`execute` 或子代理来生成 Word/docx 交付文件；使用 `create_word_document`，并依赖工具内 Markdown 到 Word 转换和 storage 登记 run-scoped artifact。

## 错误处理

- API route 把缺失/无效状态映射为 `HTTPException`，常见状态码为 400、401/403、404、409、413。
- 请求体校验错误被转换为前端可读的稳定消息。
- runner 超时、取消和异常都要写入终端事件和 task 状态。
- tool-call partial 参数流必须限流并截断持久化 payload；最终完整 tool call 仍可保留完整参数，避免字符级 partial 把 Postgres/SSE/前端日志拖垮。
- 记忆 recall、资源 manifest 或事件 payload 生成失败时，如果不影响主 run，应记录并降级继续。
- 工具函数对预期失败返回结构化错误或用户可读错误字符串，不应让 agent run 崩溃。

## 横切关注点

- 日志：服务模块使用 `logging.getLogger(__name__)`。
- 校验：Pydantic、storage path validators、upload validators 和 secret scanner 共同承担边界校验。
- 认证：`backend/app/main.py` 支持 bearer/header/query token；query token 主要服务 SSE 兼容但有 URL 暴露风险。
- 配置：`backend/app/config.py` 读取 `.env` 和环境变量；文档只引用变量名，不引用真实值。
- 测试：`create_app(...)` 支持 fake 依赖，`backend/tests/fakes.py` 是主要内存 storage fake。

---

*架构分析：2026-05-24*
