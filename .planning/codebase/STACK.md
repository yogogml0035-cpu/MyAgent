# 技术栈

**分析日期：** 2026-05-19

## 语言

- Python 3.11+：后端 FastAPI、DeepAgents 运行时、存储、streaming、工具和测试。
- TypeScript/TSX：Next.js 前端、React 组件、状态转换、API adapter 和前端测试。
- JavaScript ES modules：Playwright E2E specs。
- Bash：WSL 服务 runner 和端口清理脚本。
- PowerShell：Windows 到 WSL 的本地开发启动脚本。
- Markdown：项目文档、知识包、skills 和 `.planning` 事实文档。

## 运行时和包管理

- 后端用 `uv` 管理依赖，配置在 `backend/pyproject.toml`，锁文件是 `backend/uv.lock`。
- 前端用 `npm` 管理依赖，配置在 `frontend/package.json`，锁文件是 `frontend/package-lock.json`。
- 后端默认本地端口是 `8001`。
- 前端默认本地端口是 `3001`。
- Node 版本由 `.nvmrc` 和 CI 约束为 20。
- Python 版本由 `.python-version` 和后端配置约束为 3.11。

## 主要框架

- FastAPI：后端 HTTP API、middleware、CORS、请求限制和健康检查。
- Uvicorn：本地 ASGI 服务。
- Pydantic：后端请求/响应 schema。
- DeepAgents：agent graph、任务级文件系统、skills 和 subagents。
- LangChain / LangGraph：模型、工具、streaming 和 store 接口。
- Next.js app router：前端页面和构建运行时。
- React：聊天工作区组件。
- TypeScript strict mode：前端类型检查。

## 测试和质量工具

- pytest / pytest-asyncio：后端测试。
- Ruff：后端 lint。
- mypy：后端类型检查。
- Node `node:test` + `tsx`：前端单元和源码边界测试。
- ESLint + `eslint-config-next`：前端 lint，warning 也按失败处理。
- Playwright：浏览器 E2E 和截图证据。
- `git diff --check`：文档和空白检查。

## 关键依赖

- `deepagents`：核心 agent graph。
- `langchain-deepseek`：默认 DeepSeek 模型 provider。
- `langchain-openai`、`langchain-anthropic`：可选 provider 支持。
- `psycopg[binary]`：Postgres 访问。
- `httpx`：SearXNG、Qdrant、embedding HTTP 调用。
- `python-multipart`：文件上传。
- `python-docx`、`openpyxl`：Word 和 Excel 上传资源读取。
- `next`、`react`、`react-dom`：前端应用。
- `react-markdown`、`remark-gfm`：Markdown 展示。

## 基础设施依赖

- Postgres：任务、运行、消息、事件、缓存和长期记忆行。
- Qdrant：长期记忆向量索引。
- DashScope-compatible embeddings：长期记忆向量生成。
- SearXNG：本地搜索工具。
- 本地文件系统：上传和产物 bytes。

## 配置边界

- 后端秘密配置只放 `backend/.env` 或后端运行环境。
- 前端只能使用浏览器安全的 `NEXT_PUBLIC_*`。
- `WEB_CONCURRENCY`、`UVICORN_WORKERS`、`GUNICORN_WORKERS` 不能大于 1。
- 真实 `.env` 文件不应进入文档、测试夹具或知识包。
