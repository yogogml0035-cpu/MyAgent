# MyAgent 前端

这是本地 MyAgent 应用的 Next.js App Router 前端。

## 初始化

从 WSL 开发时，应始终使用 WSL 路径：

```bash
cd /mnt/d/AgentProject/MyAgent/frontend
```

不要先在 Windows 路径 `D:\AgentProject\MyAgent\frontend` 安装依赖或生成 Next 产物，再从 WSL 路径 `/mnt/d/AgentProject/MyAgent/frontend` 启动开发服务。混用两种路径会让 Next.js 生成包含 Windows 路径的 React Client Manifest，而服务端又按 WSL 路径解析。开发服务写入 `.next-dev`，生产构建写入 `.next`；两个输出目录都应保持环境本地化，不要在 Windows 和 WSL 之间复用。

类型检查会运行 `next typegen && tsc --noEmit`。生成的 `next-env.d.ts` 已被忽略，不应提交。

如果已经发生过路径混用，请从 WSL 清理并重新安装：

```bash
rm -rf .next .next-dev node_modules
npm ci
npm run dev
```

前端读取 `NEXT_PUBLIC_MYAGENT_API_BASE_URL`。当它为空或设为 `auto` 时，浏览器会根据当前页面主机名推导后端地址为 `http://<hostname>:8001`，因此 `http://localhost:3001` 会映射到 `http://localhost:8001`，`http://127.0.0.1:3001` 会映射到 `http://127.0.0.1:8001`。仍然支持 `http://localhost:8001` 这类显式后端地址。若修改前端 origin 或后端端口，请同步更新 `NEXT_PUBLIC_MYAGENT_API_BASE_URL` 和后端 `MYAGENT_CORS_ORIGINS`。

为兼容已迁移的本地配置，旧变量名 `NEXT_PUBLIC_API_BASE_URL` 仍然可用。

## E2E 验收

每次 bug 修复、功能新增或其他行为变更后，都应针对真实应用运行浏览器端 E2E，并把截图证据保存到 `frontend/e2e-playwright/` 下。

- 保留 `frontend/e2e-playwright/README.md` 作为目录说明。
- 保存截图时按场景或任务创建子目录。
- 不要保存会暴露客户敏感文档、token 或密钥的截图。

预期后端端点：

- `POST /api/tasks` 创建任务。
- `POST /api/tasks/{task_id}/files` 以 multipart form data 上传 Markdown 或 JSON 文件。
- `POST /api/tasks/{task_id}/messages` 发送用户消息。
- `POST /api/tasks/{task_id}/cancel` 停止任务。
- `GET /api/tasks/{task_id}` 获取任务状态、消息、日志和产物。

前端提供模型选择按钮，但菜单刻意限制为两个 DeepSeek V4 Flash 选项：`deepseek-v4-flash` 和 `deepseek-v4-flash-thinking`。provider 密钥必须只保存在后端 `.env` 中；浏览器只发送这些由后端注册过的安全模型 ID。
