# 后端代码结构

**分析日期：** 2026-05-19

## 目录布局

```text
backend/
├── app/
│   ├── api/                # FastAPI 路由
│   ├── agent/              # DeepAgents 构建和 middleware
│   ├── execution/          # 上传资源读取和检查
│   ├── models/             # 模型注册和 provider 创建
│   ├── runner/             # TaskRunner 生命周期
│   ├── security/           # 敏感内容扫描和脱敏
│   ├── streaming/          # stream adapter、event converter、SSE helper
│   ├── subagents/          # 内置 subagent 定义
│   ├── tools/              # 平台工具注册
│   ├── config.py           # Settings 和模型注册表
│   ├── main.py             # FastAPI app factory
│   ├── schemas.py          # 公共 API schema
│   └── storage.py          # Postgres 状态和本地文件存储
├── skills/                 # DeepAgents runtime skills
├── storage/                # 本地任务 workspace，默认不提交
├── tests/                  # pytest 测试
├── pyproject.toml          # 依赖和工具配置
└── uv.lock                 # 后端锁文件
```

## 关键目录职责

- `backend/app/api/`：HTTP 接口边界，新增公开接口优先放这里。
- `backend/app/agent/`：DeepAgents 创建、filesystem backend、state backend、store backend 和额外 middleware。
- `backend/app/execution/`：上传资源 inspect/read 工具。
- `backend/app/models/`：模型 ID 校验、provider 创建和可用性判断。
- `backend/app/runner/`：任务运行、取消、终态、final answer 和 memory write。
- `backend/app/security/`：密钥和敏感文本扫描。
- `backend/app/streaming/`：LangGraph v2 chunk 到平台事件的转换。
- `backend/app/tools/`：资源工具和 SearXNG 搜索注册。
- `backend/tests/`：后端验证。

## 重要文件

- `backend/app/main.py`：ASGI app 和依赖注入。
- `backend/app/api/tasks.py`：任务创建、消息、取消、历史、事件轮询。
- `backend/app/api/files.py`：上传接口。
- `backend/app/api/artifacts.py`：产物接口。
- `backend/app/api/streaming.py`：SSE 接口。
- `backend/app/storage.py`：Postgres 和本地文件 workspace。
- `backend/app/runner/core.py`：runner 核心生命周期。
- `backend/app/agent/factory.py`：DeepAgents graph 创建。
- `backend/app/streaming/v2_adapter.py`：原始 stream 适配。
- `backend/app/streaming/event_converter.py`：平台事件转换。
- `backend/app/memory.py`：长期记忆服务。

## 新代码放置规则

- 新 API：路由放 `backend/app/api/`，公共 schema 放 `backend/app/schemas.py`，测试放 `backend/tests/unit/api/`。
- 新存储契约：改 `backend/app/storage.py`，同步 `backend/tests/fakes.py` 和 storage/API/runner 测试。
- 新 run 或事件行为：改 `backend/app/runner/`、`backend/app/streaming/`，同步前端投影测试。
- 新上传资源能力：改 `backend/app/execution/resources.py` 和 `backend/app/tools/registry.py`。
- 新模型 provider：改 `backend/app/config.py`、`backend/app/models/provider.py` 和 model tests。

## 特殊目录

- `backend/storage/sessions/`：运行时任务 workspace，保存上传和产物。
- `backend/.venv/`、`.pytest_cache/`、`.mypy_cache/`、`.ruff_cache/`、`__pycache__/`：本地生成内容，不提交。
- `backend/skills/`：可提交的 runtime skill 目录。
