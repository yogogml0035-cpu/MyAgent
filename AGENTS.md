# MyAgent Agent 协作规范

本文件是仓库级长期规则，适用于整个 `/mnt/d/AgentProject/MyAgent`。它负责约束协作边界、验证入口和知识包路由；主题级长期知识进入 `asset/`，一次性过程日志不要写入长期文档。

## 仓库事实

- 后端：`backend/`，FastAPI + `uv`，入口为 `backend/app/main.py`。
- 前端：`frontend/`，Next.js app router，主界面在 `frontend/app/page.tsx`。
- 默认任务存储：`backend/storage/sessions/`。
- 后端测试：`backend/tests/`，当前任务工作流集成套件在 `backend/tests/workflow/test_workflow.py`。
- 前端测试：`frontend/tests/`，按 `state/`、`workspace/`、`upload/`、`model/` 分类，文件名必须以 `test_` 开头。
- 长期知识包索引：`asset/README.md`。
- 当前唯一长期主知识包：`asset/task_workspace_runtime_knowledge_pack.md`，覆盖任务运行、前端工作区、模型提供方、安全边界、上传限制、产物访问和测试布局。

## 工作前必须读取

- 涉及后端任务生命周期、API、存储、权限、模型或分析流程时，先读相关 `backend/app/` 代码和 `backend/tests/`。
- 涉及前端表单、任务状态、URL 映射、产物打开或轮询时，先读 `frontend/app/page.tsx`、`frontend/app/task-state.ts` 和 `frontend/tests/`。
- 涉及长期规则或已形成稳定主题边界时，先读 `asset/README.md`，再读索引中列出的相关知识包。
- 搜索优先用 `rg` 或 `rg --files`。

## 知识包读取与同步

- 影响稳定业务规则、输入输出、用户路径、运行边界或测试入口时，必须在 `asset/` 下新增或更新对应知识包。
- 更新知识包前，优先更新 `asset/README.md` 中的索引。
- 优先更新已有主题包；只有形成独立长期边界且无法并入现有主题时，才允许新建知识包。
- 知识包只沉淀稳定边界、同步面、验证入口与回归风险，不保留单次排障时间线、临时脚本路径或已删除文件名。
- 知识包至少包含：背景与范围、业务规则、输入输出样例、边界条件、已知坑点、关联代码路径、关联测试路径。
- 保留知识包时优先问两个问题：未来需求是否会反复用到；是否描述了代码/产品边界而不是单机操作步骤。若答案是否定的，把少量可复用提醒并入 `AGENTS.md` 或 `README.md`，删除独立知识包。

## 测试必须同步

- 后端行为变化至少补或更新 API、任务生命周期、存储、权限、模型路由或分析服务测试。
- 前端行为变化至少补或更新表单、状态转换器、URL 映射、产物请求或注册表测试。
- 影响关键用户路径时，再补创建任务、上传文件、发送消息、事件轮询、完成状态、产物打开/下载的集成验证；必要时补 E2E。
- 所有新增、拆分或重命名的测试文件名称必须以 `test_` 开头。Python 测试使用 `test_*.py`；前端 Node 测试使用 `test_*.test.ts`。
- 测试文件必须按测试类型分类到对应模块目录。后端当前集成/工作流测试放在 `backend/tests/workflow/`；新增窄域测试按 `api/`、`runtime/`、`storage/`、`security/`、`analysis/` 等模块建目录。前端当前分类为 `frontend/tests/state/`、`frontend/tests/workspace/`、`frontend/tests/upload/`、`frontend/tests/model/`。
- 调整测试目录或命名时，必须同步测试 runner、`README.md`、`asset/README.md`、相关知识包和本文件中的测试路径。
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

- `asset/task_workspace_runtime_knowledge_pack.md`：任务 API、状态机、runner、事件日志、版本化产物、本地 JSON 存储、前端任务工作区、文件上传、消息提交、状态轮询、日志合并、产物打开、provider 密钥、环境变量、访问令牌、CORS、本地优先安全边界、上传/JSON 限制和测试布局。
- `asset/README.md` 是唯一有效索引；新增、删除或改名知识包时必须同步更新。

### 需求修改后的知识回写路由

- 改后端任务 API、状态机、任务 runner、取消/中断、事件日志、产物下载、本地存储、前端任务创建、文件上传、消息提交、状态轮询、日志合并、产物 URL、模型提供方、环境变量、访问令牌、CORS、本地优先安全边界、上传/JSON 限制或测试布局：优先沉淀到 `asset/task_workspace_runtime_knowledge_pack.md`。
- 改 Markdown/JSON 招投标文档分类、围串标分析类别、sub-agent 分派、证据归一化、报告生成：默认先更新 `asset/task_workspace_runtime_knowledge_pack.md` 中的相关稳定边界；若形成独立长期主题，先在 `asset/README.md` 登记，再新增或更新 `asset/bid_analysis_workflow_knowledge_pack.md`。
- 改本地启动脚本、WSL 端口清理或开发终端启动方式：通常只更新 `README.md` 和本文件的本地开发建议；只有脚本演进为跨需求复用的稳定子系统时，才单独新增知识包。
- 上述文件名是建议路由；若 `asset/README.md` 已存在更合适主包，以索引为准。
- 若新规则会影响未来多数需求，再把它从知识包提升写回 `AGENTS.md`。

## 本地开发参考与建议

- 默认后端开发端口为 `8001`，默认前端开发端口为 `3001`；前端 `auto` API base 默认按页面 hostname 访问后端 `8001`。
- WSL 本地开发脚本在 `scripts/`：`start-dev-wsl.sh` 负责开前后端终端，`stop-dev-ports.sh` 负责释放默认或指定端口。
- 修改本地脚本时至少运行 `bash -n scripts/start-dev-wsl.sh`、`bash -n scripts/stop-dev-ports.sh`、对应 `--help`/`--dry-run` 和 `git diff --check`。
- 同一个 `frontend/.next` 目录只运行一个 `next dev`；并行开发服务可能污染生成产物。
- 启动脚本不得嵌入 provider 密钥、访问令牌、客户文档路径或本机私密绝对路径。非 loopback 访问仍必须遵守访问令牌与 CORS 边界。

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
