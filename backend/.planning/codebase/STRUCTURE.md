# 后端代码结构

**分析日期：** 2026-05-24

## 目录布局

```text
backend/
|-- app/                         # FastAPI 后端包
|   |-- api/                     # REST 与 SSE 路由
|   |-- agent/                   # DeepAgents/LangGraph 构建和 middleware 边界
|   |-- contracts/               # event/resource/artifact dataclass 合同
|   |-- execution/               # task-scoped 资源执行工具
|   |-- models/                  # 模型 registry/provider/DeepSeek thinking adapter
|   |-- runner/                  # 进程内任务运行编排
|   |-- security/                # secret 扫描与脱敏
|   |-- session/                 # event log 到 task/session state 的投影
|   |-- skills/                  # 项目技能文件发现
|   |-- streaming/               # LangGraph stream adapter、event converter、SSE helpers
|   |-- subagents/               # 内置 DeepAgents subagent 定义
|   |-- tools/                   # 平台工具 registry 和 SearXNG 工具
|   |-- main.py                  # FastAPI composition root
|   |-- config.py                # Settings、env loading、model registry、worker guard
|   |-- storage.py               # Postgres task/event store 和本地文件 workspace
|   |-- schemas.py               # Pydantic API DTO
|   |-- memory.py                # 长期记忆、Qdrant、DashScope embeddings
|   |-- agent_store.py           # LangGraph BaseStore 的 storage adapter
|   |-- conversation_context.py  # 同会话上下文构建
|   |-- permissions.py           # workspace/command permission policy
|   |-- reasoning_trace.py       # reasoning trace payload helper
|   `-- task_titles.py           # 自动任务标题生成
|-- skills/                      # 用户可选项目技能
|-- tests/                       # pytest 测试套件
|-- storage/                     # 本地运行时 task workspace；不是源码
|-- tmp/                         # 本地临时数据
|-- .planning/codebase/          # 后端事实文档
|-- .env.example                 # 安全配置示例
|-- .env                         # 本地私密配置；不要读取或引用值
|-- pyproject.toml               # Python 依赖和工具配置
|-- uv.lock                      # uv lockfile
`-- README.md                    # 后端安装/运行/测试文档
```

## 目录职责

- `backend/app/`：后端主包，包含 app、路由、服务、持久化、模型 provider、工具集成和运行时 helper。
- `backend/app/api/`：浏览器可见 REST/SSE endpoint，按 tasks/files/artifacts/streaming/models/skills 分面组织。
- `backend/app/agent/`：构建 DeepAgents/LangGraph agent，管理 workspace、skills、store、model、tool wiring。
- `backend/app/runner/`：`TaskRunner`、runner protocol、background task、终态事件和 run finalization。
- `backend/app/streaming/`：把 LangGraph v2 stream chunk 规范化为平台事件并格式化 SSE 终止消息。
- `backend/app/execution/`：上传资源的 inspect/read/list/table 工具和执行边界。
- `backend/app/tools/`：DeepAgents 内置工具外的平台工具注册，主要是 resource tools 与 SearXNG。
- `backend/app/models/`：安全 app-level 模型 ID、provider factory、DeepSeek thinking adapter。
- `backend/app/contracts/`：event/resource/artifact dataclass 合同和 payload builder。
- `backend/app/session/`：根据 event log 投影 task/session state。
- `backend/app/security/`：敏感信息扫描、脱敏和测试 helper。
- `backend/app/skills/`：解析 `SKILL.md` frontmatter，生成浏览器安全技能列表。
- `backend/app/subagents/`：研究、编码、文件分析等内置 subagent 定义。
- `backend/skills/`：项目技能源文件，运行时只读挂载给 agent。
- `backend/tests/`：unit/integration/e2e pytest 测试。
- `backend/storage/`：默认本地 task 文件根；运行时数据，不当源码修改。
- `backend/.planning/codebase/`：本文件所在的后端事实层。

## 关键文件

### 入口与配置

- `backend/app/main.py`：app factory、ASGI `app`、middleware、router 注册、lifespan startup。
- `backend/app/config.py`：`Settings`、环境变量读取、模型 registry、单 worker guard。
- `backend/app/memory_admin.py`：Qdrant reset/rebuild CLI。
- `backend/pyproject.toml`：依赖、pytest、Ruff、mypy、uv source pin。
- `backend/.env.example`：安全变量名来源。

### API 路由

- `backend/app/api/tasks.py`：任务 CRUD、message send、run start/cancel、事件读取。
- `backend/app/api/files.py`：上传 endpoint。
- `backend/app/api/artifacts.py`：artifact 下载 endpoint。
- `backend/app/api/streaming.py`：基于持久化事件的 SSE endpoint。
- `backend/app/api/models.py`：模型列表。
- `backend/app/api/skills.py`：项目技能列表。

### 核心逻辑

- `backend/app/runner/core.py`：agent run 生命周期和 background run 管理。
- `backend/app/agent/factory.py`：DeepAgent 构建与 workspace/skills backend 路由。
- `backend/app/storage.py`：数据库表、task 状态、events、uploads、artifacts、memory rows、agent store rows。
- `backend/app/memory.py`：记忆 recall/extract/index，Qdrant 和 DashScope-compatible embedding。
- `backend/app/conversation_context.py`：同会话上下文和 tool-cache context。
- `backend/app/execution/resources.py`：上传资源工具实现。
- `backend/app/tools/searxng_search.py`：SearXNG 工具与结果缓存。

### 合同与 DTO

- `backend/app/schemas.py`：Pydantic 请求/响应模型。
- `backend/app/contracts/__init__.py`：资源、产物、事件 dataclass 和稳定 ID helper。
- `backend/app/session/projector.py`：event log 投影合同。

### 测试

- `backend/tests/fakes.py`：与 storage public surface 对齐的内存 fake。
- `backend/tests/unit/api/`：API route 行为测试。
- `backend/tests/unit/runner/`：runner、上下文、并发、记忆测试。
- `backend/tests/unit/storage/`：storage、agent store、artifact/upload 不变量测试。
- `backend/tests/unit/streaming/`：stream adapter 和 event converter 测试。
- `backend/tests/unit/tools/`：resource/search 工具测试。
- `backend/tests/integration/`：Postgres、memory、agent build 集成测试。
- `backend/tests/e2e/`：API/SSE E2E 测试。

## 命名约定

- Python 模块使用 `snake_case`：`conversation_context.py`, `task_titles.py`。
- pytest 文件使用 `test_*.py`，按 `unit/<layer>/`, `integration/`, `e2e/` 分组。
- 项目技能目录和 frontmatter name 保持一致，技能文件必须叫 `SKILL.md`。
- 类、Pydantic model、dataclass 使用 `PascalCase`：`Settings`, `TaskRunner`, `PostgresTaskStorage`, `EventRecord`。
- 函数、方法、fixture 使用 `snake_case`：`create_app`, `load_settings`, `start_background`。
- 模块常量使用 `UPPER_SNAKE_CASE`：`MODEL_REGISTRY`, `UPLOAD_FORMATS`, `RUN_ARTIFACT_NAMES`。

## 新代码落位

- 新 REST endpoint：放在 `backend/app/api/` 或最接近的现有 router；必要时更新 `backend/app/schemas.py` 和 `backend/app/main.py`。
- 新 task lifecycle 行为：HTTP 校验在 `tasks.py`，执行行为在 `runner/core.py`，持久化在 `storage.py`。
- 新持久化数据：先更新 `storage.py` public method 和表结构，再同步 `schemas.py`、`tests/fakes.py` 和测试。
- 新 agent tool：放在 `backend/app/tools/<name>.py` 或 `backend/app/execution/<domain>.py`，并在 `get_platform_tools(...)` 注册。
- 新上传资源能力：扩展 `LocalResourceExecutionAdapter` 与 `create_resource_tools(...)`。
- 新模型/provider：更新 `backend/app/config.py` 的 `MODEL_REGISTRY`、`backend/app/models/registry.py` 和 `backend/app/models/provider.py`。
- 新项目技能：新增 `backend/skills/<skill>/SKILL.md`，包含 `name` 和 `description` frontmatter。
- 新长期记忆功能：以 `backend/app/memory.py` 为主，先补 Postgres canonical storage，再考虑 Qdrant 行为。
- 新 stream event：先在 `v2_adapter.py` 规范化，再在 `event_converter.py` 映射并补 streaming tests。
- 新安全/权限规则：secret scanner 在 `security/scanner.py`，workspace/command 权限在 `permissions.py`，HTTP auth/body limit 在 `main.py`。

## 特殊目录

- `backend/.venv/`, `.mypy_cache/`, `.pytest_cache/`, `.ruff_cache/`：本地生成，不能提交。
- `backend/storage/`：默认运行时 task workspace，session 内容不当源码处理。
- `backend/tmp/`：本地临时数据。
- `backend/.planning/codebase/`：生成的后端事实文档，按任务需要提交。
- `backend/skills/`：项目技能源码，需提交。
- `backend/tests/`：源码级测试，需提交。

---

*结构分析：2026-05-24*
