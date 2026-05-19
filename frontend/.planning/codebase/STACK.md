# 前端技术栈

**分析日期：** 2026-05-19

## 语言和运行时

- TypeScript/TSX：应用、组件、hook、状态转换和测试。
- JavaScript ES modules：Playwright specs。
- CSS：全局设计系统和组件样式。
- Node.js 20：前端运行和 CI 目标。
- npm：依赖管理，锁文件是 `frontend/package-lock.json`。

## 主要框架和库

- Next.js app router：页面、构建和开发服务。
- React / React DOM：聊天工作区 UI。
- TypeScript strict mode：类型检查。
- react-markdown：Markdown 渲染。
- remark-gfm：GitHub-flavored Markdown 支持。
- Playwright：浏览器 E2E。
- tsx + Node `node:test`：TypeScript 单元测试。
- ESLint + eslint-config-next：lint。

## 脚本

```bash
cd frontend
npm run dev
npm run typecheck
npm test
npm run lint
npm run build
npm run e2e:runtime-contracts
```

## 配置文件

- `frontend/package.json`：scripts 和依赖。
- `frontend/package-lock.json`：依赖锁定。
- `frontend/tsconfig.json`：TypeScript strict 配置。
- `frontend/eslint.config.mjs`：ESLint 配置和忽略目录。
- `frontend/next.config.mjs`：Next `distDir` 和 watcher 配置。
- `frontend/.env.example`：浏览器安全 env 示例。

## 环境变量

- `NEXT_PUBLIC_MYAGENT_API_BASE_URL`：后端 API base URL。
- `NEXT_PUBLIC_API_BASE_URL`：旧版 API base URL。
- `NEXT_PUBLIC_MYAGENT_TOKEN`：浏览器可见访问 token。
- `NEXT_PUBLIC_AGENT_CHAT_TOKEN`：旧版浏览器 token。
- `MYAGENT_E2E_BASE_URL`、`MYAGENT_E2E_API_URL`、`MYAGENT_E2E_EVIDENCE_DIR`：E2E 运行配置。

## 注意事项

- `NEXT_PUBLIC_*` 会暴露给浏览器，不能保存 provider key、数据库 URL 或客户资料。
- 前端没有自己的 API route；任务能力依赖后端。
- 本地 dev 默认端口是 `3001`。
- E2E 截图证据保存到 ignored 目录，不提交 git。
