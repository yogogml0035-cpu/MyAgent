# MyAgent Agent 协作规范

本文件是仓库级长期规则，适用于整个 `/mnt/d/AgentProject/MyAgent`。主题级、能力级、排障后沉淀的长期知识进入 `asset/`，不要把一次性过程日志塞进本文件。

## 仓库事实

- 后端：`backend/`，FastAPI + `uv`，入口为 `backend/app/main.py`。
- 前端：`frontend/`，Next.js app router，主界面在 `frontend/app/page.tsx`。
- 默认任务存储：`backend/storage/tasks/`。
- 后端测试：`backend/tests/test_workflow.py`。
- 前端测试：`frontend/tests/task-state.test.ts`。
- 长期知识包索引：`asset/README.md`。

## 工作前必须读取

- 涉及后端任务生命周期、API、存储、权限、模型或分析流程时，先读相关 `backend/app/` 代码和 `backend/tests/`。
- 涉及前端表单、任务状态、URL 映射、产物打开或轮询时，先读 `frontend/app/page.tsx`、`frontend/app/task-state.ts` 和 `frontend/tests/`。
- 涉及长期规则或已形成稳定主题边界时，先读 `asset/README.md`，再读索引中列出的相关知识包。
- 搜索优先用 `rg` 或 `rg --files`。

## 样例与知识包必须同步

- 影响稳定业务规则、输入输出、用户路径、运行边界或测试入口时，必须在 `asset/` 下新增或更新对应知识包。
- 更新知识包前，优先更新 `asset/README.md` 中的索引。
- 优先更新已有主题包；只有形成独立长期边界且无法并入现有主题时，才允许新建知识包。
- 知识包只沉淀稳定边界、同步面、验证入口与回归风险，不保留单次排障时间线、临时脚本路径或已删除文件名。
- 知识包至少包含：背景与范围、业务规则、输入输出样例、边界条件、已知坑点、关联代码路径、关联测试路径。

## 测试必须同步

- 后端行为变化至少补或更新 API、任务生命周期、存储、权限、模型路由或分析服务测试。
- 前端行为变化至少补或更新表单、状态转换器、URL 映射、产物请求或注册表测试。
- 影响关键用户路径时，再补创建任务、上传文件、发送消息、事件轮询、完成状态、产物打开/下载的集成验证；必要时补 E2E。
- 只改文档时至少运行 `git diff --check`，并说明未运行代码测试的理由。

## 最低交付标准

- 对行为变更，代码、测试、知识包三者缺一不可。
- 只补代码，不补测试或知识包，视为未完成。
- 如果某次修改确实不需要知识包，必须在交付说明中明确原因，例如“仅修正文案/格式，未改变稳定业务规则或运行边界”。

## `asset/` 的使用规范

### `asset/` 定位

- `asset/` 是长期项目上下文源，不只是复盘目录。
- 智能体处理具体类型或能力时，应优先读取相关知识包，而不是把整个仓库文档全量灌入上下文。
- 知识包内容必须脱敏，禁止放入客户原文、密钥、访问令牌或其他敏感数据。

### 知识沉淀收敛规范

- `AGENTS.md` 只保存跨主题、跨多次需求都会复用的仓库级边界；topic 级长期知识进入 `asset/`。
- `asset/` 中同一共享规则只能有一个主包；其他知识包只引用，不重复复制同一段边界说明。
- 旧包被新主包完整吸收后必须删除，不保留 old/new 并行版本。
- 知识包必须只引用当前仍存在的代码、测试、命令和目录；禁止继续引用已删除文件、本地样本路径、worktree 操作说明或按日期展开的 patch 时间线。
- 一次故障复盘只能沉淀为“触发条件 + 稳定边界 + 验证信号 + 回归风险”，不能把修复过程日志直接当长期知识。

### 当前有效知识包

- 当前还没有主题知识包。
- `asset/README.md` 是唯一有效索引；新增主题包前必须先更新该索引。

### 需求修改后的知识回写路由

- 改后端任务 API、状态机、任务 runner、取消/中断、事件日志、产物下载或本地存储：优先沉淀到 `asset/backend_task_runtime_knowledge_pack.md`。
- 改 Markdown 招投标文档分类、围串标分析类别、sub-agent 分派、证据归一化、报告生成：优先沉淀到 `asset/bid_analysis_workflow_knowledge_pack.md`。
- 改前端任务创建、文件上传、消息提交、状态轮询、日志合并、产物 URL 或打开逻辑：优先沉淀到 `asset/frontend_task_workspace_knowledge_pack.md`。
- 改模型提供方、环境变量、访问令牌、CORS、本地优先安全边界或上传/JSON 限制：优先沉淀到 `asset/model_provider_security_knowledge_pack.md`。
- 上述文件名是建议路由；若 `asset/README.md` 已存在更合适主包，以索引为准。
- 若新规则会影响未来多数需求，再把它从知识包提升写回 `AGENTS.md`。

## 运行与验证命令

后端：

```bash
cd backend
uv run pytest
uv run ruff check .
uv run mypy app tests
```

前端：

```bash
cd frontend
npm run typecheck
npm test
npm run lint
npm run build
```

文档/空白检查：

```bash
git diff --check
```

## 安全与运行边界

- `DEEPSEEK_API_KEY`、`TAVILY_API_KEY` 等 provider 密钥只能放在 `backend/.env` 或后端运行环境中。
- `NEXT_PUBLIC_*` 会暴露给浏览器，不能写入 provider 密钥、客户数据或私密样例。
- 任务 API 默认只允许 loopback；对非本机访问必须配置 `MYAGENT_ACCESS_TOKEN` 并同步前端 `NEXT_PUBLIC_MYAGENT_TOKEN`。
- 当前后端使用进程内 runner 和本地 JSON 任务存储，不允许多 worker 部署；不要绕过 `WEB_CONCURRENCY`、`UVICORN_WORKERS`、`GUNICORN_WORKERS` 的单进程保护。
- 不要把上传的真实客户文档、生成的敏感报告、密钥、令牌或本地绝对私密路径写入文档、测试夹具或知识包。

## 交付说明要求

- 说明改了哪些文件和为什么。
- 说明运行了哪些验证命令。
- 若未补测试或知识包，说明原因。
- 若发现用户需求本身会引入错误边界、过度设计或安全风险，必须直接指出并给出更稳妥的替代方案。
