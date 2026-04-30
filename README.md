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
backend/storage/sessions/ 默认本地任务和产物存储目录
frontend/                Next.js app-router 前端
frontend/app/            UI 和任务状态映射代码
frontend/tests/          前端测试，按 state/workspace/upload/model 分类
asset/                   面向后续智能体协作的长期知识包索引
```

## 环境要求

- Python 3.11 或更新版本
- 用于后端依赖管理的 `uv`
- 与当前 Next.js 版本兼容的 Node.js 和 npm
- 用于真实模型调用的 DeepSeek API Key
- 可选：用于联网搜索分析工具的 Tavily API Key

## WSL 路径约定

推荐在 WSL shell 中使用 Linux 路径运行本仓库，当前仓库路径为：

```bash
cd /mnt/d/AgentProject/MyAgent
```

前端依赖、`.next` 缓存和开发服务应在同一个环境内生成和运行。不要在 Windows 的 `D:\AgentProject\MyAgent\frontend` 下安装依赖后，再从 WSL 的 `/mnt/d/AgentProject/MyAgent/frontend` 启动 `npm run dev`；反向混用也一样会让 Next.js 的 React Client Manifest 同时出现 Windows 路径和 WSL 路径。

如果已经混用过 Windows 和 WSL，请在 WSL 中清理前端产物并重新安装依赖：

```bash
cd /mnt/d/AgentProject/MyAgent/frontend
rm -rf .next node_modules
npm ci
```

## 安装

安装后端依赖：

```bash
cd /mnt/d/AgentProject/MyAgent/backend
uv sync --dev
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
MYAGENT_ACCESS_TOKEN=
MYAGENT_CORS_ORIGINS=http://localhost:3001,http://127.0.0.1:3001
MYAGENT_TASK_ROOT=
MYAGENT_MAX_UPLOAD_FILES=10
MYAGENT_MAX_UPLOAD_FILE_BYTES=10485760
MYAGENT_MAX_UPLOAD_REQUEST_BYTES=105906176
MYAGENT_MAX_JSON_REQUEST_BYTES=65536
DEEPSEEK_TIMEOUT_SECONDS=15
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
NEXT_PUBLIC_MYAGENT_TOKEN=
```

模型提供方凭据必须只放在后端。任何带有 `NEXT_PUBLIC_` 前缀的值都会暴露给浏览器。

## 本地开发启动

WSL 中可直接用仓库脚本清理端口，并打开两个新的 WSL 终端分别启动前后端：

```bash
cd /mnt/d/AgentProject/MyAgent
./scripts/start-dev-wsl.sh
```

脚本会先停止 WSL 内监听后端端口 `8001` 和前端端口 `3001` 的进程，然后通过 Windows Terminal 分别打开两个 WSL 窗口：

- 后端：`uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8001`
- 前端：`next dev -p 3001 -H 0.0.0.0`

启动后可以在各自终端中用 `Ctrl+C` 停止单个服务，也可以回到仓库运行 `./scripts/stop-dev-ports.sh` 统一释放端口。该脚本依赖 WSL 可调用的 `wt.exe` 和 `wsl.exe`。

如果只需要释放端口：

```bash
cd /mnt/d/AgentProject/MyAgent
./scripts/stop-dev-ports.sh
```

可用环境变量或参数覆盖端口：

```bash
BACKEND_PORT=8002 FRONTEND_PORT=3002 ./scripts/start-dev-wsl.sh
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

## 本地部署说明

后端按单一本地进程设计。在任务 runner 和 JSON 存储重新设计之前，不要使用多个 Uvicorn、Gunicorn 或平台 worker 运行。应用会通过 `WEB_CONCURRENCY`、`UVICORN_WORKERS` 或 `GUNICORN_WORKERS` 拒绝大于 1 的 worker 数量。

本地生产风格运行前端：

```bash
cd /mnt/d/AgentProject/MyAgent/frontend
npm run build
npm run start
```

单独运行后端：

```bash
cd /mnt/d/AgentProject/MyAgent/backend
uv run uvicorn app.main:app --host 127.0.0.1 --port 8001
```

如果任务 API 会被非 loopback 客户端访问，请在后端设置 `MYAGENT_ACCESS_TOKEN`，并在前端将相同值设置为 `NEXT_PUBLIC_MYAGENT_TOKEN`。如果任务产物需要在清理或重新部署后保留，也请将 `MYAGENT_TASK_ROOT` 设置为持久化本地目录。

如果要从局域网地址 `<LAN_IP>` 进行访问，需要显式配置前后端服务。

后端 `backend/.env`：

```env
MYAGENT_ACCESS_TOKEN=choose-a-local-token
MYAGENT_CORS_ORIGINS=http://localhost:3001,http://127.0.0.1:3001,http://<LAN_IP>:3001
```

前端 `frontend/.env.local`：

```env
NEXT_PUBLIC_MYAGENT_API_BASE_URL=auto
NEXT_PUBLIC_MYAGENT_TOKEN=choose-a-local-token
```

在可被外部访问的接口上启动服务：

```bash
cd /mnt/d/AgentProject/MyAgent/backend
uv run uvicorn app.main:app --host 0.0.0.0 --port 8001
```

```bash
cd /mnt/d/AgentProject/MyAgent/frontend
npm run dev -- -H 0.0.0.0
```

然后打开 `http://<LAN_IP>:3001`。不要把 provider key 写入任何 `NEXT_PUBLIC_*` 值；`NEXT_PUBLIC_MYAGENT_TOKEN` 只保护这个本地任务 API，并且对能够加载前端的浏览器可见。

如果服务已经在 WSL 内监听 `0.0.0.0`，但 Windows 侧的 `<LAN_IP>:3001` 或 `<LAN_IP>:8001` 仍无法连接，说明 WSL NAT 没有把 Windows LAN IP 转发到 WSL。用管理员 PowerShell 添加端口转发：

```powershell
$listenIp = "<LAN_IP>"
$wslIp = ((wsl hostname -I).Trim() -split "\s+")[0]
foreach ($port in 3001, 8001) {
  netsh interface portproxy delete v4tov4 listenaddress=$listenIp listenport=$port
  netsh interface portproxy add v4tov4 listenaddress=$listenIp listenport=$port connectaddress=$wslIp connectport=$port
  netsh advfirewall firewall add rule name="MyAgent WSL $port" dir=in action=allow protocol=TCP localport=$port
}
```

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
- `GET /api/tasks/{task_id}` 读取任务状态、消息、日志和产物。
- `GET /api/tasks/{task_id}/events` 读取增量事件记录。
- `POST /api/tasks/{task_id}/files` 上传 Markdown 或 JSON 文件。
- `POST /api/tasks/{task_id}/messages` 为任务启动或恢复工作。
- `POST /api/tasks/{task_id}/cancel` 请求取消任务。
- `GET /api/tasks/{task_id}/artifacts/{artifact_name}` 下载产物。

任务 API 默认只允许 loopback 客户端访问。配置了 `MYAGENT_ACCESS_TOKEN` 后，请求必须提供 `Authorization: Bearer <token>` 或 `X-MyAgent-Token`。
浏览器调用方还必须使用 `MYAGENT_CORS_ORIGINS` 中列出的 origin；默认只允许 `http://localhost:3001` 和 `http://127.0.0.1:3001`。

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
- 前端只发送安全模型 ID，例如 `deepseek-reasoner`。
- 上传文件、任务计划、证据、摘要、日志和 HTML 报告会存储在本地任务目录中。
- 文件访问和命令执行辅助能力默认限定在任务工作区内。
- 上传和 JSON 请求大小限制由后端环境变量控制。
- 浏览器 CORS origin 由 `MYAGENT_CORS_ORIGINS` 控制；请使用精确的协议、主机和端口，例如 `http://<LAN_IP>:3001`。
- 迁移后的本地配置仍兼容旧的 `AGENT_CHAT_*` 和 `NEXT_PUBLIC_AGENT_CHAT_*` 名称，但新配置应使用 `MYAGENT_*`。

## 常见问题

- `401 访问令牌无效或缺失。`：设置匹配的 `MYAGENT_ACCESS_TOKEN` 和 `NEXT_PUBLIC_MYAGENT_TOKEN`，然后重启两个服务。
- `403 任务 API 默认只允许本机访问；如需非本机访问，请设置 MYAGENT_ACCESS_TOKEN`：请求来自非 loopback 客户端，且没有提供访问令牌。
- `409 任务运行中不能上传文件`：停止当前任务或等待任务结束后再上传更多文件。
- `开始文档分析任务前，请先上传 Markdown 或 JSON 文件。`：任务消息需要文档分析，但尚未上传 Markdown 或 JSON 文件。
- `至少需要上传两份投标人文档才能进行对比。`：至少上传两个投标方 Markdown 或 JSON 文件以便进行比较。
