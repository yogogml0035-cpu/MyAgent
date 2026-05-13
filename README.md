# MyAgent

MyAgent 是一个本地优先的 AI 智能体工作区，用于基于 Markdown 的招投标文档分析。项目由 FastAPI 后端和 Next.js 前端组成：后端负责管理任务、运行分析 worker、持久化证据并生成报告；前端负责文件上传、任务消息、用户友好的任务直播日志、AI 回复和产物查看。

当前 V1 工作流聚焦于围标、串标类文档检查：

1. 在本地启动后端和前端。
2. 上传 Markdown 或 JSON 格式的招标、投标文档。
3. 发送类似 `帮我检查是否有串标围标嫌疑` 的任务消息。
4. 后端创建任务计划，运行分类 sub-agent，保存证据和结构化事件，并写入报告产物。
5. 任务完成后，在前端打开 `report.html` 查看结果。

## 仓库结构

```text
backend/                 FastAPI 服务、任务 runner、分析流程、本地存储
backend/app/             后端运行时代码
backend/tests/           后端测试，按类型分目录，文件名以 test_ 开头
backend/storage/sessions/ 默认上传和产物文件目录，任务状态写入 Postgres
frontend/                Next.js app-router 前端
frontend/app/            UI 和任务状态映射代码
frontend/tests/          前端测试，按 state/workspace/upload/model 分类
frontend/e2e-playwright/ 浏览器端 E2E 与网页验收截图证据目录
asset/                   面向后续智能体协作的长期知识包目录
```

## 环境要求

- Python 3.11 或更新版本
- 用于后端依赖管理的最新版 `uv`
- 与当前 Next.js 版本兼容的 Node.js 和 npm
- 本机可访问的 Postgres 与 Qdrant 服务
- 用于真实模型调用的 DeepSeek API Key
- 用于长期记忆向量化的 DashScope API Key
- 可选：用于联网搜索分析工具的 Tavily API Key

当前 README 默认覆盖“同一台机器上的本地开发和本机部署”。不再展开访问令牌配置或跨主机/LAN 暴露方案。

## WSL 路径约定

推荐在 WSL shell 中使用 Linux 路径运行本仓库，当前仓库路径为：

```bash
cd /mnt/d/AgentProject/MyAgent
```

前端依赖、Next 缓存和开发服务应在同一个环境内生成和运行。开发服务使用 `.next-dev`，生产构建使用 `.next`，两者不要互相复用。不要在 Windows 的 `D:\AgentProject\MyAgent\frontend` 下安装依赖后，再从 WSL 的 `/mnt/d/AgentProject/MyAgent/frontend` 启动 `npm run dev`；反向混用也一样会让 Next.js 的 React Client Manifest 同时出现 Windows 路径和 WSL 路径。

前端类型检查通过 `next typegen && tsc --noEmit` 生成 Next 路由类型；`frontend/next-env.d.ts` 属于生成文件，不再纳入版本控制。

如果已经混用过 Windows 和 WSL，请在 WSL 中清理前端产物并重新安装依赖：

```bash
cd /mnt/d/AgentProject/MyAgent/frontend
rm -rf .next .next-dev node_modules
npm ci
```

## 安装

### 安装最新版 uv

WSL / Linux / macOS：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv --version
```

Windows PowerShell：

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
uv --version
```

如果之前已经通过官方 installer 安装过 `uv`，可以直接升级到最新稳定版：

```bash
uv self update
```

### 安装项目依赖

安装后端依赖：

```bash
cd /mnt/d/AgentProject/MyAgent/backend
uv sync
```

如果需要把后端锁定依赖升级到当前约束允许的最新版本：

```bash
cd /mnt/d/AgentProject/MyAgent/backend
uv lock --upgrade
uv sync
```

安装前端依赖：

```bash
cd /mnt/d/AgentProject/MyAgent/frontend
npm ci
```

## 配置

从示例文件创建后端配置：

```bash
cd /mnt/d/AgentProject/MyAgent/backend
cp .env.example .env
```

后端专用配置应写入 `backend/.env`：

```env
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
TAVILY_API_KEY=
MYAGENT_DATABASE_URL=postgresql://USER:PASSWORD@127.0.0.1:5432/DBNAME
MYAGENT_QDRANT_URL=http://127.0.0.1:6333
DASHSCOPE_API_KEY=
MYAGENT_EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
MYAGENT_EMBEDDING_MODEL=text-embedding-v3
MYAGENT_EMBEDDING_DIMENSIONS=1024
MYAGENT_QDRANT_COLLECTION=myagent_memories
MYAGENT_CORS_ORIGINS=http://localhost:3001,http://127.0.0.1:3001
MYAGENT_TASK_ROOT=
MYAGENT_MAX_UPLOAD_FILES=10
MYAGENT_MAX_UPLOAD_FILE_BYTES=10485760
MYAGENT_MAX_UPLOAD_REQUEST_BYTES=105906176
MYAGENT_MAX_JSON_REQUEST_BYTES=65536
```

当前端默认值不够用时，从示例文件创建前端配置：

```bash
cd /mnt/d/AgentProject/MyAgent/frontend
cp .env.example .env.local
```

前端公开配置：

```env
# auto 会按当前页面主机名连接 http://<hostname>:8001
NEXT_PUBLIC_MYAGENT_API_BASE_URL=auto
```

模型提供方、数据库和向量服务凭据必须只放在后端。任何带有 `NEXT_PUBLIC_` 前缀的值都会暴露给浏览器。

后端启动时会强制检查 Postgres、Qdrant collection 和 DashScope embedding 探测。缺少 `MYAGENT_DATABASE_URL`、`MYAGENT_QDRANT_URL` 或 `DASHSCOPE_API_KEY`，或任一外部服务不可用，都会导致后端启动失败。Postgres 表结构由后端幂等创建；Qdrant collection 默认使用 `myagent_memories`，向量维度为 `1024`。

## 本地开发启动

从 Windows PowerShell 启动 WSL 开发环境，并打开两个新的 Windows Terminal 标签页分别运行前后端：

```powershell
cd D:\AgentProject\MyAgent
.\scripts\start-dev-wsl.ps1
```

脚本会先停止 WSL 内监听后端端口 `8001` 和前端端口 `3001` 的进程，然后通过 Windows Terminal 分别打开两个 WSL 窗口。Postgres、Qdrant 和 DashScope 配置由用户自管，脚本不会自动启动容器：

- 后端：`WATCHFILES_FORCE_POLLING=true uv run uvicorn app.main:app --reload --reload-delay 0.25 --host 127.0.0.1 --port 8001`
- 前端：`NEXT_DIST_DIR=.next-dev WATCHPACK_POLLING=true CHOKIDAR_USEPOLLING=true CHOKIDAR_INTERVAL=300 next dev -p 3001 -H 127.0.0.1`

启动后可以在各自终端中用 `Ctrl+C` 停止单个服务，也可以回到 WSL 仓库路径运行 `./scripts/stop-dev-ports.sh` 统一释放端口。启动脚本依赖 Windows 侧可调用的 `wt.exe` 和 `wsl.exe`。前端开发服务写入 `.next-dev`，因此运行 `npm run build` 验证生产构建时写入 `.next`，不会再覆盖正在热更新的开发缓存。

当前仓库放在 `/mnt/d` 这类 Windows 挂载盘时，WSL 里的 Linux 进程经常收不到稳定的文件系统变更事件，表现为“刷新页面不生效，必须重启服务”。开发脚本默认开启轮询 watcher 来保证前端热更新和后端 `uvicorn --reload` 能感知修改。若仓库迁移到 WSL 原生路径（例如 `~/projects/MyAgent`）并确认热更新正常，可临时用 `MYAGENT_DEV_FORCE_POLLING=0` 关闭脚本里的轮询以降低 CPU 占用。

仓库根目录的 `.gitattributes` 负责统一换行策略，避免在 Windows、WSL 和 GitHub Web 编辑器之间来回切换时，把 YAML、Shell、TypeScript 等文本文件意外改成 CRLF。

如果 Windows 系统代理指向 `localhost` 或 `127.0.0.1`，WSL NAT 模式可能在新开 WSL 终端时报 `Wsl/Service/E_UNEXPECTED`。PowerShell 启动脚本会检测该情况，并在需要时写入 `%USERPROFILE%\.wslconfig` 的 `[wsl2] autoProxy=false` 后重启 WSL；已有自定义代理方案时可加 `-NoProxyRepair` 禁用自动修复。

如果只需要释放端口：

```bash
cd /mnt/d/AgentProject/MyAgent
./scripts/stop-dev-ports.sh
```

可用参数覆盖端口：

```powershell
.\scripts\start-dev-wsl.ps1 -BackendPort 8002 -FrontendPort 3002
```

如果确实需要让同一局域网内其他设备访问开发服务，必须显式传入 `-BackendHost 0.0.0.0 -FrontendHost 0.0.0.0`，并同步配置 `MYAGENT_ACCESS_TOKEN`、`NEXT_PUBLIC_MYAGENT_TOKEN` 和受控的 `MYAGENT_CORS_ORIGINS`。默认脚本只绑定 loopback，避免无意暴露本地开发服务。

停止对应端口：

```bash
./scripts/stop-dev-ports.sh --backend-port 8002 --frontend-port 3002
```

如果修改后端端口，请将 `frontend/.env.local` 中的 `NEXT_PUBLIC_MYAGENT_API_BASE_URL` 改成显式后端 URL，或同步调整前端解析逻辑的默认端口。

停止脚本面向 WSL 进程，使用 `lsof`、`fuser` 或 `ss` 查找监听进程；如果端口由 Windows 侧进程占用，需要在 Windows 侧关闭对应应用。

启动后端：

```bash
cd /mnt/d/AgentProject/MyAgent/backend
uv run uvicorn app.main:app --reload --port 8001
```

在另一个终端启动前端：

```bash
cd /mnt/d/AgentProject/MyAgent/frontend
npm run dev
```

打开：

```text
http://localhost:3001
```

健康检查：

```bash
curl http://localhost:8001/health
```

## 测试与验收要求

对每次 bug 修复、功能新增或其他行为变更，除了对应的单元、集成、类型、lint 和构建验证外，还必须：

1. 启动实际后端与前端服务。
2. 运行与本次需求对应的浏览器端 E2E 场景；如果仓库里没有现成入口，需要在同次修改中补齐。
3. 在网页端完成验收截图，并将图片证据保存到 `frontend/e2e-playwright/`。

`frontend/e2e-playwright/README.md` 负责说明这个目录的用途、命名建议和脱敏要求。

## 本机部署与启动

后端按单一本地进程设计。虽然任务状态、运行、消息和事件日志已经由 Postgres 持久化，但任务 runner 仍然是进程内调度；不要使用多个 Uvicorn、Gunicorn 或平台 worker 运行。应用会通过 `WEB_CONCURRENCY`、`UVICORN_WORKERS` 或 `GUNICORN_WORKERS` 拒绝大于 1 的 worker 数量。

部署前，先确认后端 lockfile 仍然有效，并安装运行时依赖：

```bash
cd /mnt/d/AgentProject/MyAgent/backend
uv lock --check
uv sync --no-dev
```

任务状态、运行、消息和事件日志保存在 Postgres；上传文件和报告产物保存在 `MYAGENT_TASK_ROOT` 指向的本地目录。需要重启后保留文件产物时，请把 `MYAGENT_TASK_ROOT` 设置到持久化目录。

构建并启动前端：

```bash
cd /mnt/d/AgentProject/MyAgent/frontend
npm ci
npm run build
npm run start
```

在另一个终端启动后端：

```bash
cd /mnt/d/AgentProject/MyAgent/backend
uv run uvicorn app.main:app --host 127.0.0.1 --port 8001
```

然后打开 `http://localhost:3001`。当前 README 仅覆盖本机访问路径：前端运行在 `3001`，后端运行在 `8001`，两者位于同一台机器上。

本仓库目前不包含 Docker、进程管理器、反向代理、TLS 或多主机部署文件。将它作为生产服务前，需要显式补齐这些能力。

## 使用流程

1. 在前端创建或复用一个任务。
2. 上传文件名为 `.md` 或 `.json` 的文档文件。
3. 发送描述所需分析的用户消息。
4. 查看任务直播中的工具调用、结果摘要、回答生成状态和产物创建过程。
5. 任务完成后打开生成的产物，尤其是 `report.html`。

如果没有上传文件，且消息看起来不像招投标文档分析请求，后端支持简单聊天。文档分析请求必须上传 Markdown 或 JSON 文件。

## API 概览

- `GET /health` 返回服务健康状态。
- `GET /api/models` 列出暴露给前端的安全模型 ID。
- `POST /api/tasks` 创建任务。
- `GET /api/tasks` 读取历史会话摘要，历史标题优先使用用户重命名后的自定义标题。
- `GET /api/tasks/{task_id}` 读取任务状态、消息、日志和产物。
- `PATCH /api/tasks/{task_id}` 重命名历史会话标题。
- `DELETE /api/tasks/{task_id}` 删除非运行中的历史会话及其本地任务文件。
- `GET /api/tasks/{task_id}/events` 读取增量事件记录。
- `POST /api/tasks/{task_id}/files` 上传 Markdown 或 JSON 文件。
- `POST /api/tasks/{task_id}/messages` 为任务启动或恢复工作。
- `POST /api/tasks/{task_id}/cancel` 请求取消任务。
- `GET /api/tasks/{task_id}/artifacts/{artifact_name}` 下载产物。

当前 README 默认按 `localhost` / `127.0.0.1` 访问说明。浏览器 origin 仍受 `MYAGENT_CORS_ORIGINS` 约束；如果你修改前端访问地址或端口，需要同步更新后端允许的 origin。

## 验证

运行后端测试和检查：

```bash
cd /mnt/d/AgentProject/MyAgent/backend
uv run pytest
uv run ruff check .
uv run mypy app tests
```

运行前端检查：

```bash
cd /mnt/d/AgentProject/MyAgent/frontend
npm run typecheck
npm test
npm run lint
npm run build
```

仅修改文档时运行：

```bash
git diff --check
```

## 运行边界

- Provider 凭据只能作为后端 `.env` 值保存。
- 前端只发送安全模型 ID，例如 `deepseek:deepseek-chat`。
- 任务状态、运行、消息和事件日志写入 Postgres；上传文件、任务计划、证据、摘要和 HTML 报告等文件产物保存在本地任务目录中。
- Qdrant 只保存成功任务的高层长期记忆摘要，不保存上传原文、完整产物正文、流式 token 或工具原始日志。
- 文件访问和命令执行辅助能力默认限定在任务工作区内。
- 上传和 JSON 请求大小限制由后端环境变量控制。
- 浏览器 CORS origin 由 `MYAGENT_CORS_ORIGINS` 控制；当前默认值允许 `http://localhost:3001` 和 `http://127.0.0.1:3001`。

## 常见问题

- `403 任务 API 默认只允许本机访问。`：当前 README 只覆盖本机部署；请确认你访问的是 `http://localhost:3001` 或 `http://127.0.0.1:3001`，并且后端监听在本机 `8001` 端口。
- `409 任务运行中不能上传文件`：停止当前任务或等待任务结束后再上传更多文件。
- `开始文档分析任务前，请先上传 Markdown 或 JSON 文件。`：任务消息需要文档分析，但尚未上传 Markdown 或 JSON 文件。
- `至少需要上传两份投标人文档才能进行对比。`：至少上传两个投标方 Markdown 或 JSON 文件以便进行比较。
