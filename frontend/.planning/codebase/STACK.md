# 前端技术栈

**分析日期：** 2026-05-24

## 语言

- TypeScript：应用逻辑、React 组件、hooks、API adapter、unit tests。
- TSX / React JSX：chat workspace 组件和 App Router entry。
- JavaScript / ESM：Next、ESLint、Playwright 配置和 specs。
- CSS：`frontend/app/globals.css` 的全局样式和设计 token。
- SVG：app icon 和少量组件内图形。

## 运行时和包管理

- 浏览器运行时：DOM APIs、EventSource、File、FormData、Blob、Clipboard、Window popup。
- Node.js：Next、tests、lint、build、Playwright。
- 包管理：npm，lockfile 为 `frontend/package-lock.json`。
- `frontend/package.json` 未声明 `packageManager` 或 `engines`；Next dependency 自身约束 Node 版本。

## 核心框架

- Next.js 15：App Router、metadata、dev/build/start。
- React 19：client component state、effects 和 rendering。
- React DOM：浏览器渲染。
- `react-markdown`：渲染 AI Markdown。
- `remark-gfm`：支持 GitHub-flavored Markdown。

## 测试与开发工具

- Node `node:test`：通过 `tsx` 运行 TypeScript 单测。
- `tsx`：Node tests 的 TypeScript loader。
- Playwright / `@playwright/test`：浏览器 E2E。
- TypeScript compiler：`next typegen && tsc --noEmit`。
- ESLint flat config：`eslint-config-next` 的 core web vitals 和 TypeScript 规则。
- PostCSS：由 package override 固定。

## 关键依赖

- `next`：routing、build output、dev server、production server。
- `react`, `react-dom`：交互式 task workspace。
- `react-markdown`, `remark-gfm`：AI markdown 展示。
- `@playwright/test`：浏览器验收。
- `typescript`, `tsx`：类型检查和 TypeScript tests。
- `eslint`, `eslint-config-next`：lint。
- `@types/node`, `@types/react`, `@types/react-dom`：类型声明。

## 配置

- `NEXT_PUBLIC_MYAGENT_API_BASE_URL`：后端 base URL；`auto` 或未设置时由当前页面 hostname 推导 `:8001`。
- `NEXT_PUBLIC_API_BASE_URL`：legacy fallback。
- `NEXT_PUBLIC_MYAGENT_TOKEN`：可选浏览器访问 token。
- `NEXT_PUBLIC_AGENT_CHAT_TOKEN`：legacy token fallback。
- `NEXT_WATCH_POLL_INTERVAL_MS`：Next watch polling interval，默认 `300`。
- `.env.local` 可能存在但被忽略，不能读取或文档化真实值。

## package scripts 脚本

```bash
cd frontend
npm run dev                 # Next dev on 3001, 使用 polling env
npm run build               # Next production build
npm run start               # next start -p 3001
npm run typecheck           # next typegen && tsc --noEmit
npm test                    # Node unit tests through tsx
npm run lint                # eslint . --max-warnings=0
npm run e2e:runtime-contracts
```

## 构建配置

- `frontend/next.config.mjs`：dev 输出 `.next-dev`，production 输出 `.next`。
- `frontend/tsconfig.json`：`strict: true`、`moduleResolution: "bundler"`、`jsx: "preserve"`。
- `frontend/eslint.config.mjs`：忽略 `.next/**`、`.next-dev*/**`、`node_modules/**`、`next-env.d.ts`。
- `frontend/.gitignore`：忽略依赖、Next 输出、coverage、tsbuildinfo、generated env、`.env*.local`。

## 平台要求

- 默认本地前端端口 `3001`，后端端口 `8001`。
- WSL 开发建议使用 `/mnt/d/AgentProject/MyAgent/frontend`，避免混用 Windows/WSL 生成物。
- 后端 CORS 必须允许前端 origin；改 API base URL 时同步检查后端 CORS。
- provider secrets 留在后端，浏览器只发送安全 model ID 和可选本地访问 token。

## 生产事实

- 生产命令是 `npm run build` 后 `npm run start`。
- 默认 production port 为 `3001`。
- 当前仓库未确认 hosting provider、deployment adapter 或 CI deployment workflow。

---

*技术栈分析：2026-05-24*
