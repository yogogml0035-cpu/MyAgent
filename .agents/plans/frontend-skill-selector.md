# 功能: Frontend Skill Selector

下面这份计划应尽可能完整，但在真正开始实现前，你仍然必须再次验证文档、代码库模式以及任务本身是否合理。

特别注意现有 utils、types、models 的命名，并确保从正确的文件中导入。

## 功能描述

在 MyAgent 聊天输入区增加 `/` skill 选择体验：用户输入 `/` 后看到当前项目 `backend/skills` 下所有可用 skill，按名称或描述筛选，点击或键盘确认后在 composer 内显示 Codex 风格 skill chip。用户继续输入自然语言需求并发送后，后端能收到结构化 skill 名称，并把 skill 引用保留为用户可见消息内容的一部分。

第一版不做浏览器内 skill 编辑、版本管理、路径展示或 Codex 全局 skill 暴露。前端只展示 `name` 和 `description`，后端只扫描仓库内 `backend/skills`。

## 用户故事

作为一名 MyAgent 本地工作台用户
我想要在聊天输入框中输入 `/` 后选择当前项目的 skill
以便不用记忆 skill 名称，也不会误选本机其他全局 skill。

## 问题陈述

当前前端没有 skill 发现与选择入口。用户需要手动知道可用 skill 名称，或者只能依赖模型自动判断。仓库已有 `backend/skills/code_review/SKILL.md` 和 `backend/skills/web_research/SKILL.md`，但这部分能力没有安全地投影到浏览器，也没有与 composer 输入体验整合。

## 方案陈述

新增一个只读后端 endpoint `GET /api/skills`，固定读取仓库 `backend/skills` 下的 `SKILL.md` frontmatter，并只返回 `name` 与 `description`。前端在 `useTaskWorkspace()` 初始化时加载 skill 列表，传给 `ChatComposer`。

`ChatComposer` 复用现有 textarea，不切换到 contenteditable。选中 skill 后，在同一个 `.composerPanel` 内 textarea 上方显示 compact chip，并从 textarea 中移除 `/query` 触发 token。发送时，前端把已选 skill 名称作为结构化字段传给后端；后端校验 skill 是否存在，再把消息格式化为带 skill mention 的文本传给 storage/runner，从而让用户消息卡片和 agent 输入都能看到该 skill 引用。

这个取舍优先保留现有 IME、Enter 发送、上传文件、模型选择、停止任务等行为。chip 是 composer 内的真实控件，不是普通文本；消息发送边界用结构化 `skills` 字段避免浏览器暴露本地路径。

## 功能元数据

**功能类型**: 新能力  
**预估复杂度**: 中  
**主要受影响系统**: FastAPI API、skill discovery、Next.js composer、任务消息请求、前端样式、前后端测试、Playwright E2E、平台知识包  
**依赖项**: 现有 FastAPI、Pydantic、React 19、Next.js 15、Playwright；不需要新增 npm 或 Python 依赖

---

## 上下文参考

### 相关代码文件 重要：实现前你必须先阅读这些文件！

- `tasks/prd-frontend-skill-selector.md` - PRD 权威来源；包含只展示 `backend/skills`、Codex 风格 chip、发送闭环和 E2E 验收。
- `AGENTS.md` - 仓库执行边界；前端行为/视觉变更必须同步测试、浏览器 E2E、截图证据和知识包。
- `DESIGN.md` - 视觉依据；保持暖色画布、珊瑚主色、克制圆角和现有 CSS token。
- `backend/app/skills/loader.py` (lines 1-61) - 已有 `SKILL.md` frontmatter 解析与目录扫描；返回包含 `path`，新 API 不能把 `path` 透出给浏览器。
- `backend/app/api/models.py` (lines 1-16) - 最接近的新只读 API 模式：`APIRouter(prefix="/api")`、response_model、从 `request.app.state.settings` 读取上下文。
- `backend/app/main.py` (lines 17-23, 85-96, 106-113) - API router 注册位置与全 `/api/` 鉴权中间件；新增 `/api/skills` 后自动受 token/loopback 保护。
- `backend/app/schemas.py` (lines 1-29, 74-90) - Pydantic schema 放置位置；`MessageRequest` 当前只有 `message/model/mode/input_scope`。
- `backend/app/api/tasks.py` (lines 1-18, 145-166) - `send_message()` 是消息提交边界；可在这里校验 selected skills 并格式化最终消息。
- `backend/app/config.py` (lines 32-35, 76-91) - `settings.skills_dirs` 用于 agent runtime，但本功能要求前端只看仓库 `backend/skills`，不要使用 `MYAGENT_SKILLS_DIRS` 作为浏览器列表来源。
- `backend/skills/code_review/SKILL.md` - 默认项目 skill 示例：`name: code-review`。
- `backend/skills/web_research/SKILL.md` - 默认项目 skill 示例：`name: web-research`。
- `backend/tests/unit/skills/test_loader.py` - skill loader 现有单测模式，覆盖空目录、坏 frontmatter、重复 name、多目录扫描。
- `backend/tests/unit/skills/test_builtin_skill_content.py` - 默认 `backend/skills` 内容断言；可作为 endpoint 期望数据参考。
- `backend/tests/unit/api/test_tasks.py` (top fixtures and `TestClient` pattern) - API 单测 fixture 模式；使用 `Settings(...)` + `InMemoryTaskStorage`。
- `backend/tests/unit/security/test_auth.py` - `/api/` token/loopback 鉴权测试模式；新增 `/api/skills` 不需要绕过。
- `frontend/lib/task-api.ts` (lines 1-70, 149-153) - 前端 API adapter 和 token header 统一入口；新增 `fetchSkillOptions()` 与扩展 `postTaskMessage()`。
- `frontend/app/task-state.ts` (lines 202-215, 266-314, 1089-1100) - 前端类型、`isRecord/readString`、请求 payload builder、normalize pattern；适合新增 `SkillOption` 和 `normalizeSkillOption()`。
- `frontend/hooks/use-task-workspace.ts` (lines 164-187, 246-278, 412-464) - 工作区状态、初始化加载模型/历史、发送成功清空输入；需要新增 skill 列表和 selected skills 状态。
- `frontend/components/chat/TaskWorkspace.tsx` (lines 35-52) - hook 到 composer 的 props 传递点。
- `frontend/components/chat/ChatComposer.tsx` (lines 17-34, 54-89, 100-111, 125-175, 177-274) - composer props、关闭弹层、Enter 发送、文件预览、textarea、模型 picker 和发送按钮。
- `frontend/app/globals.css` (lines 1-49, 1791-2055, 2055-2345, 2360-2468) - 设计 token、composer panel、file chip、model picker menu、mobile composer grid；skill chip/menu 应复用这些视觉模式。
- `frontend/tests/state/test_task_state.test.ts` - 前端纯 helper 测试模式；适合测试 skill normalize、slash trigger、message payload。
- `frontend/tests/workspace/test_task_workspace.test.ts` - hook/source 边界和 composer source assertions。
- `frontend/tests/workspace/test_workspace_view.test.ts` (composer CSS alignment test around current CSS assertions) - 样式回归测试模式。
- `frontend/e2e-playwright/README.md` - E2E 截图证据目录与运行方式；新增行为必须有 Playwright spec 和 ignored evidence。
- `frontend/e2e-playwright/test_upload_preview_design.spec.mjs` - composer 视觉/交互 E2E 模式：真实页面、截图、CSS 断言、移动端 viewport。
- `asset/deepagents_platform_knowledge_pack.md` - 平台长期知识包；新增 `/api/skills` 和 composer skill 选择边界后必须同步。
- `INTERFACES.md` - 跨系统接口文档；新增 Browser to Backend skill endpoint 和消息 payload 字段后必须同步。

### 需要创建的新文件

- `backend/app/api/skills.py` - 只读 skill 列表 API：`GET /api/skills`。
- `backend/app/skills/project.py` - 项目 skill 目录定位、浏览器安全列表投影、skill name 校验、消息 skill mention 格式化。
- `backend/tests/unit/api/test_skills.py` - `/api/skills` endpoint 单测。
- `backend/tests/unit/skills/test_project_skills.py` - 项目 skill projection、去路径、validate/format helper 单测。
- `frontend/app/skill-selection.ts` - skill option 类型、normalize、筛选、slash trigger 查找/替换、可见消息辅助函数。
- `frontend/tests/state/test_skill_selection.test.ts` - skill helper 单测。
- `frontend/e2e-playwright/test_skill_selector.spec.mjs` - 真实浏览器 skill selector 验收和截图。

### 需要更新的现有文件

- `backend/app/schemas.py` - 新增 `SkillOption` schema；给 `MessageRequest` 增加 `skills: list[str]`，建议限制数量和单项长度。
- `backend/app/main.py` - import/register `skills_router`。
- `backend/app/api/tasks.py` - 在 `send_message()` 中校验 `body.skills` 并格式化给 storage/title/runner 的消息。
- `frontend/app/task-state.ts` - 更新 `MessageRequestPayload`，导入/转发 skill normalize helper 或保留现有 request builder 语义。
- `frontend/lib/task-api.ts` - 新增 `fetchSkillOptions()`；`postTaskMessage(id, content, model, skills)` 发送 `skills`。
- `frontend/hooks/use-task-workspace.ts` - 维护 `skillOptions`、`selectedSkills`、加载失败提示、发送成功/失败清理规则。
- `frontend/components/chat/TaskWorkspace.tsx` - 传递 skill props。
- `frontend/components/chat/ChatComposer.tsx` - 增加 chip shelf、slash picker、键盘导航、选择/删除 handlers。
- `frontend/app/globals.css` - skill chip/menu/responsive styles。
- `frontend/tests/state/test_task_state.test.ts`、`frontend/tests/workspace/test_task_workspace.test.ts`、`frontend/tests/workspace/test_workspace_view.test.ts` - 补 source/behavior/CSS 回归断言。
- `frontend/e2e-playwright/README.md` - 增加 skill selector spec 运行说明。
- `INTERFACES.md`、`asset/deepagents_platform_knowledge_pack.md` - 同步新 API 和安全边界。

### 相关文档 实现前你应该先阅读这些文档！

- `tasks/prd-frontend-skill-selector.md`
  - 具体章节：User Stories、Functional Requirements、Non-Goals。
  - 原因：验收口径权威来源。
- `AGENTS.md`
  - 具体章节：前端表单/任务状态阅读顺序、必守执行边界、知识回写。
  - 原因：此变更涉及前端交互、后端 API、E2E 和知识包。
- `DESIGN.md`
  - 具体章节：colors、rounded、text-input、button/icon 视觉约束。
  - 原因：skill chip/menu 必须保持现有暖色画布体系。
- `frontend/e2e-playwright/README.md`
  - 具体章节：evidence 目录规则和 composer 相关 spec 运行示例。
  - 原因：行为变更必须有真实浏览器截图证据。
- `asset/deepagents_platform_knowledge_pack.md`
  - 具体章节：Skills、API routes、Browser E2E、Known Pitfalls。
  - 原因：新增 skill projection 是平台稳定边界。

外部调研：本功能不引入新库，不需要外部 API 或浏览器新特性；依赖现有 FastAPI/Pydantic/React/Playwright 模式即可。不要为了 chip 把 composer 改成 contenteditable，除非后续明确接受 IME、selection、a11y 和 Enter 行为重写成本。

### 需要遵循的模式

**后端 API 路由：**

- 新 endpoint 使用 `APIRouter(prefix="/api", tags=["skills"])`，类似 `backend/app/api/models.py`。
- 在 `backend/app/main.py` 顶部 import router，并在 `create_app()` 中 `app.include_router(...)`，位置靠近 models router。
- 所有 `/api/` 请求会走 `authorize_task_request()`，不要为 `/api/skills` 做特殊豁免。

**后端 skill 投影：**

- 复用 `discover_skills([str(project_skills_dir)])`，但 response 只保留 `name` 和 `description`。
- 项目 skill 目录用代码定位到仓库 `backend/skills`，不要使用 `settings.skills_dirs` 或 `MYAGENT_SKILLS_DIRS`。这样符合“只展示当前项目 backend/skills”。
- `discover_skills()` 会跳过坏 frontmatter 和重复 name；endpoint 不要把这些作为 500。

**消息 selected skills：**

- `MessageRequest` 增加 `skills`，前端发送 `skills: ["web-research"]`。
- `send_message()` 需要校验所有 skill 名称都存在于项目 skill 集；未知名称返回 400，detail 使用用户可读中文。
- 传给 `storage.start_run()`、`_set_auto_title_if_empty()` 和 `runner.start_background()` 的应是同一个最终消息字符串，例如：
  - `[$web-research]\n\n搜索今天的 AI 新闻`
  - 多个 skill：`[$code-review] [$web-research]\n\n...`
- 如果没有正文但有文件，继续使用现有 `DEFAULT_FILE_PROMPT`，再叠加 skill mention。

**前端状态边界：**

- API 调用只放在 `frontend/lib/task-api.ts`。
- 后端 payload 归一化放在 `frontend/app/task-state.ts` 或新的纯 helper `frontend/app/skill-selection.ts`，组件不直接猜后端字段。
- React 副作用放在 `frontend/hooks/use-task-workspace.ts`，`ChatComposer` 只处理 UI 局部状态、slash token、键盘导航和 focus。

**Composer UI：**

- 保留 textarea；skill chip shelf 放在 `.composerPanel` 内、textarea 上方。
- slash picker 作为 menu，不是卡片嵌套卡片；视觉复用 model picker 的 border/background/shadow，但用 skill 专属 class，避免误绑模型样式。
- 关闭行为沿用 model picker 模式：打开时监听外部 pointerdown 和 Escape。
- Enter 发送仍走 `shouldSubmitComposerKey()`，但当 skill picker 打开时，Enter 优先选择当前 option，ArrowUp/ArrowDown 调整 active option，Escape 关闭 picker。

**测试模式：**

- 后端 API 使用 `TestClient(create_app(settings, storage=InMemoryTaskStorage(...)))`。
- 前端 helper 用 Node `test` + `assert`，source boundary 测试读取文件文本。
- E2E 使用 Playwright spec，真实打开 `/`，截图存入 `MYAGENT_E2E_EVIDENCE_DIR`。

---

## 实现计划

### 阶段 1：后端安全 skill 投影

建立项目 skill 列表的权威后端边界，只返回浏览器安全字段。

**任务：**

- 创建 `backend/app/skills/project.py`。
- 新增 `SkillOption` schema。
- 新增 `GET /api/skills` 并注册路由。
- 单测验证只返回 `backend/skills` 的 name/description，不返回 path/body。

### 阶段 2：消息 skill 引用传递

让前端选择的 skill 以结构化字段进入后端，并由后端格式化成用户可见且 runner 可读的消息文本。

**任务：**

- 扩展 `MessageRequest.skills`。
- 在 `send_message()` 校验 skill name。
- 格式化最终消息后再调用 storage/title/runner。
- 更新后端 API 测试，覆盖有效/未知 skill。

### 阶段 3：前端 skill 数据和 composer 交互

加载 skill 列表、实现 slash trigger、筛选、chip、删除、键盘导航和发送清理。

**任务：**

- 新增 `SkillOption` 前端类型和 helpers。
- 新增 `fetchSkillOptions()`。
- `useTaskWorkspace()` 维护 skill options 和 selected skills。
- `ChatComposer` 显示 chip shelf 和 skill picker。
- 发送成功清空 selected skills；发送失败保留。

### 阶段 4：样式、文档和验证

完善视觉、测试、E2E 和知识回写。

**任务：**

- 增加 CSS 并覆盖桌面/移动布局。
- 增加 frontend Node tests 和 Playwright spec。
- 更新 `INTERFACES.md`、`asset/deepagents_platform_knowledge_pack.md`、`frontend/e2e-playwright/README.md`。
- 运行完整前后端验证和真实浏览器 E2E，保存截图证据。

---

## 分步任务

重要：严格按顺序执行所有任务，从上到下。每个任务都必须是原子性的，并且可独立测试。

### CREATE `backend/app/skills/project.py`

- **IMPLEMENT**: 提供 `project_skills_dir() -> Path`、`list_project_skill_options() -> list[dict[str, str]]`、`project_skill_names() -> set[str]`、`validate_project_skill_names(names: list[str]) -> list[str]`、`format_message_with_skill_refs(message: str, skill_names: list[str]) -> str`。
- **PATTERN**: 复用 `backend/app/skills/loader.py:25-61` 的 `discover_skills()`。
- **IMPORTS**: `from pathlib import Path`; `from app.skills.loader import discover_skills`。
- **GOTCHA**: `Path(__file__).resolve().parents[2] / "skills"` 才是 `backend/skills`；不要使用当前工作目录或 `settings.skills_dirs`。返回给浏览器的数据必须删除 `path`。
- **VALIDATE**: `cd backend && uv run pytest tests/unit/skills/test_loader.py`

### UPDATE `backend/app/schemas.py`

- **IMPLEMENT**: 新增 `class SkillOption(BaseModel): name: str; description: str = ""`。给 `MessageRequest` 添加 `skills: list[str] = Field(default_factory=list, max_length=8)`；如使用 Pydantic item constraints，保持 mypy 通过。
- **PATTERN**: 现有 `ModelOption` 在同文件内定义，`MessageRequest` 当前位于 lines 21-25。
- **IMPORTS**: 继续使用现有 `BaseModel, Field`。
- **GOTCHA**: 不要把 skill path/body 放入 schema。`MAX_MESSAGE_CHARS` 仍只约束正文 message；skill 数量/单项长度另行限制。
- **VALIDATE**: `cd backend && uv run mypy app tests`

### CREATE `backend/app/api/skills.py`

- **IMPLEMENT**: `router = APIRouter(prefix="/api", tags=["skills"])`；`@router.get("/skills", response_model=list[SkillOption])` 返回 `list_project_skill_options()`。
- **PATTERN**: 镜像 `backend/app/api/models.py:1-16` 的只读 API shape。
- **IMPORTS**: `from fastapi import APIRouter`; `from app.schemas import SkillOption`; `from app.skills.project import list_project_skill_options`。
- **GOTCHA**: 不要读取 `Request` 或 settings，避免 env 配置改变浏览器可见范围。
- **VALIDATE**: `cd backend && uv run pytest tests/unit/api/test_skills.py`（创建测试后运行）

### UPDATE `backend/app/main.py`

- **IMPLEMENT**: import `skills_router` 并在 `create_app()` 中 `app.include_router(skills_router)`。
- **PATTERN**: 当前 routers import 在 lines 17-22，include 在 lines 91-95。
- **IMPORTS**: `from .api.skills import router as skills_router`。
- **GOTCHA**: `/api/skills` 会自动经过 lines 106-113 的 `/api/` 鉴权，不能绕过。
- **VALIDATE**: `cd backend && uv run pytest tests/unit/security/test_auth.py`

### UPDATE `backend/app/api/tasks.py`

- **IMPLEMENT**: 在 `send_message()` 中读取 `body.skills`，用 `validate_project_skill_names()` 校验；有未知 skill 时 `HTTPException(status_code=400, detail="未知 skill：...")`。生成 `effective_message = format_message_with_skill_refs(body.message, body.skills)`，后续 `storage.start_run()`、`_set_auto_title_if_empty()`、`runner.start_background()` 都使用 `effective_message`。
- **PATTERN**: 模型校验和错误使用现有 `_validate_runnable_model()`、`HTTPException` 模式；发送边界在 lines 145-166。
- **IMPORTS**: `from app.skills.project import format_message_with_skill_refs, validate_project_skill_names`。
- **GOTCHA**: `storage.start_run()` 成功后到 `runner.start_background()` 之间不要增加会抛出未捕获异常的非关键逻辑。未知 skill 必须在 `storage.start_run()` 前失败。
- **VALIDATE**: `cd backend && uv run pytest tests/unit/api/test_tasks.py`

### CREATE `backend/tests/unit/skills/test_project_skills.py`

- **IMPLEMENT**: 测试 `list_project_skill_options()` 包含 `code-review` 和 `web-research`，每项只包含 `name/description`，不包含 `path`。测试 `format_message_with_skill_refs("hello", ["web-research"])` 输出含 `[$web-research]` 和 `hello`。测试空 skills 返回原 message。
- **PATTERN**: 参考 `backend/tests/unit/skills/test_builtin_skill_content.py` 的内置 skill 定位和断言。
- **IMPORTS**: `from app.skills.project import ...`。
- **GOTCHA**: 不要依赖测试执行当前工作目录；helper 内部必须自己定位 `backend/skills`。
- **VALIDATE**: `cd backend && uv run pytest tests/unit/skills/test_project_skills.py`

### CREATE `backend/tests/unit/api/test_skills.py`

- **IMPLEMENT**: 用 `TestClient(create_app(settings, storage=InMemoryTaskStorage(...)))` 请求 `GET /api/skills`；断言 200、包含默认两个 skills、响应 JSON 不含 `path` 和 skill 正文。补一个 access token 场景，未带 token 返回 401，带 `X-MyAgent-Token` 返回 200。
- **PATTERN**: 参考 `backend/tests/unit/api/test_tasks.py` fixture 和 `backend/tests/unit/security/test_auth.py` token 测试。
- **IMPORTS**: `TestClient`, `Settings`, `create_app`, `InMemoryTaskStorage`。
- **GOTCHA**: `create_app()` 使用 lifespan；这个 endpoint 不需要 startup 初始化，但如测试 startup side effect，要用 context manager。
- **VALIDATE**: `cd backend && uv run pytest tests/unit/api/test_skills.py tests/unit/security/test_auth.py`

### UPDATE `backend/tests/unit/api/test_tasks.py`

- **IMPLEMENT**: 添加消息发送带 `skills: ["web-research"]` 的测试；创建 idle task 后 `POST /messages`，断言返回 messages 中 user content 包含 `[$web-research]` 与原正文。添加未知 skill 测试，断言 400 且 task 仍不是 running。
- **PATTERN**: 复用 `create_idle_task` fixture 和现有 send message 测试。
- **IMPORTS**: 无新增或只需现有 fixtures。
- **GOTCHA**: 模型需要可运行，fixture 已设置 `deepseek_api_key="sk-test"`。
- **VALIDATE**: `cd backend && uv run pytest tests/unit/api/test_tasks.py`

### CREATE `frontend/app/skill-selection.ts`

- **IMPLEMENT**: 定义 `SkillOption`、`SelectedSkill`；实现 `normalizeSkillOption(value)`, `normalizeSkillOptions(value)`, `filterSkillOptions(options, query)`, `findSkillSlashTrigger(value, caretIndex)`, `replaceSkillSlashTrigger(value, trigger)`, `dedupeSelectedSkills(skills)`。
- **PATTERN**: 纯 helper 风格参考 `frontend/app/task-state.ts` 的 `isRecord/readString/normalizeModelOption`。
- **IMPORTS**: 可从 `./task-state` 导入 `isRecord`、`readString`，或将轻量读取逻辑留在本文件。
- **GOTCHA**: `findSkillSlashTrigger()` 应只匹配当前 caret 前最近一个无空白 token：开头或空白后的 `/query`。普通 URL `https://`、正文中的斜杠路径、已经有空格的 `/web research` 不应触发。
- **VALIDATE**: `cd frontend && npm test -- tests/state/test_skill_selection.test.ts`（若 node --test glob 不支持单文件参数，则用完整 `npm test`）

### UPDATE `frontend/app/task-state.ts`

- **IMPLEMENT**: 扩展 `MessageRequestPayload` 为 `{ content, message, model, mode, skills: string[] }`；`buildMessageRequestPayload(message, model, { mode, skills })` 输出去重后的 skill names。
- **PATTERN**: 当前 builder 在 lines 305-314。
- **IMPORTS**: 从 `./skill-selection` 导入 dedupe helper，或在 task-state 内保持简短 helper。
- **GOTCHA**: 保持旧调用兼容：未传 skills 时发送 `skills: []` 或省略均可，但测试要固定预期。建议发送 `skills: []`，后端默认也接受。
- **VALIDATE**: `cd frontend && npm test`

### UPDATE `frontend/lib/task-api.ts`

- **IMPLEMENT**: import `normalizeSkillOptions` 和 `type SkillOption`；新增 `fetchSkillOptions(): Promise<SkillOption[]>` 调 `/api/skills`；更新 `postTaskMessage(id, content, model, skills = [])` 传入 `buildMessageRequestPayload(content, model, { skills })`。
- **PATTERN**: `fetchModelOptions()` lines 59-70 和 `postTaskMessage()` lines 149-153。
- **IMPORTS**: `normalizeSkillOptions` from `../app/skill-selection`。
- **GOTCHA**: 使用 `requestTaskJson()`，这样 token header 和错误格式复用现有逻辑。
- **VALIDATE**: `cd frontend && npm run typecheck`

### UPDATE `frontend/hooks/use-task-workspace.ts`

- **IMPLEMENT**: 新增 state：`skillOptions`, `selectedSkills`。初始化 effect 中并行或顺序调用 `fetchSkillOptions()`；失败时设置 warning notice 但不阻断模型/历史加载。新增 handlers：`handleSelectSkill`, `handleRemoveSkill`, `handleClearSkills`。发送时 `postTaskMessage(id, taskContent, model, selectedSkills.map(s => s.name))`；发送成功后 `setSelectedSkills([])`，catch 中保留。
- **PATTERN**: 模型 options 加载在 lines 246-278；发送成功清空 input/files 在 lines 429-438。
- **IMPORTS**: `fetchSkillOptions`；`type SkillOption/SelectedSkill`。
- **GOTCHA**: `canSend` 不必因只有 skill chip 变 true；用户仍需输入正文或选择文件。文件-only + skill 时使用现有 `DEFAULT_FILE_PROMPT` 并携带 skills。
- **VALIDATE**: `cd frontend && npm test -- tests/workspace/test_task_workspace.test.ts` 或 `cd frontend && npm test`

### UPDATE `frontend/components/chat/TaskWorkspace.tsx`

- **IMPLEMENT**: 把 `workspace.skillOptions`、`workspace.selectedSkills`、`workspace.handleSelectSkill`、`workspace.handleRemoveSkill` 传给 `ChatComposer`。
- **PATTERN**: 当前 composer props 传递在 lines 35-52。
- **IMPORTS**: 无新增类型导入，除非 prop 类型需要。
- **GOTCHA**: 不要在 `TaskWorkspace` 做业务逻辑，它只是组合层。
- **VALIDATE**: `cd frontend && npm run typecheck`

### UPDATE `frontend/components/chat/ChatComposer.tsx`

- **IMPLEMENT**: 扩展 props；新增 `textareaRef`、`skillPickerRef`、`isSkillPickerOpen`、`activeSkillIndex`、`slashTrigger`。textarea onChange 更新 input 并根据 caret 检测 slash trigger；onSelect skill 时调用 `replaceSkillSlashTrigger()` 清除 `/query`，调用 parent select handler，focus textarea 并恢复 caret。渲染 `selectedSkills` chip shelf，chip 有 remove button。渲染 skill picker menu，支持 click、ArrowUp/ArrowDown、Enter、Escape。
- **PATTERN**: 外部点击/Escape 关闭可镜像 model picker effect lines 64-89；key submit 当前在 lines 100-111；model picker menu lines 190-241。
- **IMPORTS**: 从 `../../app/skill-selection` 导入 type/helper；继续使用 React hooks。
- **GOTCHA**: 当 skill picker 打开且用户按 Enter，必须选择 skill 而不是提交表单。当 IME composing 时不要触发选择或提交。`activeTask` 为 true 时不应打开 skill picker。
- **VALIDATE**: `cd frontend && npm run typecheck && npm test`

### UPDATE `frontend/app/globals.css`

- **IMPLEMENT**: 给 `.composerPanel` 增加 `position: relative;`。新增 `.skillChipShelf`, `.skillChip`, `.skillChipIcon`, `.removeSkillButton`, `.skillPicker`, `.skillPickerMenu`, `.skillOption`, `.skillOption-active`, `.skillEmptyState` 等样式。桌面 menu 贴近 textarea；`.hasConversation` 时向上展开或保持不遮挡 sticky footer；移动端适配 `.composerControls` grid。
- **PATTERN**: file chip 视觉在 composer CSS 附近；model menu 视觉在 `.modelPickerMenu` 和 `.modelOption`。
- **IMPORTS**: CSS 无 imports。
- **GOTCHA**: 不要新增离散色系；使用 `--surface`, `--surface-card`, `--hairline`, `--primary`, `--muted`。文字必须 ellipsis 或自然换行，不能溢出。
- **VALIDATE**: `cd frontend && npm test -- tests/workspace/test_workspace_view.test.ts`

### CREATE `frontend/tests/state/test_skill_selection.test.ts`

- **IMPLEMENT**: 测试 normalize 只保留 name/description；filter 按 name/description 大小写不敏感；slash trigger 覆盖 `/`, `/web`, `hello /code`、URL/path 不触发；replace 后移除 `/query`；dedupe 保持顺序。
- **PATTERN**: `frontend/tests/state/test_task_state.test.ts` 的 Node `test` + `assert`。
- **IMPORTS**: helper functions from `../../app/skill-selection`。
- **GOTCHA**: 测试中文 description 匹配，确保 `web-research` 的中文说明也可搜索。
- **VALIDATE**: `cd frontend && npm test`

### UPDATE `frontend/tests/state/test_task_state.test.ts`

- **IMPLEMENT**: 增加 `buildMessageRequestPayload("搜索", "deepseek-v4-flash", { skills: ["web-research"] })` 断言 payload 包含 `skills: ["web-research"]`，且默认调用包含空 skills 或按约定省略。
- **PATTERN**: 当前 message payload 测试在该文件中已有。
- **IMPORTS**: 无新增。
- **GOTCHA**: 如果选择省略空 skills，测试和后端默认要一致。
- **VALIDATE**: `cd frontend && npm test`

### UPDATE `frontend/tests/workspace/test_task_workspace.test.ts`

- **IMPLEMENT**: 添加 source boundary 测试：`ChatComposer.tsx` 包含 skill picker role/listbox、skill chip shelf、remove handler；`use-task-workspace.ts` 调用 `fetchSkillOptions`，发送成功清空 `setSelectedSkills([])`，catch 前不清空。
- **PATTERN**: 现有文件通过 `readFileSync()` 做源码边界断言。
- **IMPORTS**: 无新增。
- **GOTCHA**: Source assertions 不替代行为测试，只用于防止结构漂移。
- **VALIDATE**: `cd frontend && npm test`

### UPDATE `frontend/tests/workspace/test_workspace_view.test.ts`

- **IMPLEMENT**: 添加 CSS 断言：`.skillChipShelf`、`.skillPickerMenu`、`.skillOption-active` 存在；颜色使用 `var(--surface*)`/`var(--primary)`；不出现路径展示相关 class 文案。
- **PATTERN**: composer CSS alignment 测试使用 regex 匹配 CSS。
- **IMPORTS**: 无新增。
- **GOTCHA**: 不要写过脆的像素测试；只断言关键布局、安全和 token。
- **VALIDATE**: `cd frontend && npm test`

### CREATE `frontend/e2e-playwright/test_skill_selector.spec.mjs`

- **IMPLEMENT**: 真实打开 `/`；等待 placeholder `尽管问...`；输入 `/`；断言列表包含 `code-review`、`web-research` 且不包含 `SKILL.md`/本地路径。截图 `01-skill-menu-open.png`。输入 `/web` 断言只显示 `web-research`。点击 `web-research`，断言 chip 可见、textarea 不含 `/web`。继续输入“搜索今天的 AI 新闻”，点击发送，断言用户消息包含 `web-research` 和正文。截图 desktop 和 mobile。
- **PATTERN**: `test_upload_preview_design.spec.mjs` 使用 `BASE_URL`、`EVIDENCE_DIR`、`page.goto("/")`、截图和 CSS 断言。
- **IMPORTS**: `fs`, `path`, `{ expect, test }`。
- **GOTCHA**: 如果发送会因为模型未配置被阻止，E2E 可以只验证发送前的 payload via route interception，或要求测试服务配置 `DEEPSEEK_API_KEY=sk-test` 并在后端 fake provider 可用。优先复用现有真实服务；不要 mock 静态页面。
- **VALIDATE**: `cd frontend && MYAGENT_E2E_BASE_URL=http://127.0.0.1:3001 MYAGENT_E2E_EVIDENCE_DIR=./e2e-playwright/e2e-$(date +%Y%m%d%H%M%S)/skill-selector npx playwright test e2e-playwright/test_skill_selector.spec.mjs --reporter=line`

### UPDATE `frontend/e2e-playwright/README.md`

- **IMPLEMENT**: 添加 skill selector spec 的运行命令和截图证据说明。
- **PATTERN**: 参考 upload-preview-design 章节。
- **IMPORTS**: 无。
- **GOTCHA**: 不要提交 `e2e-YYYYMMDDHHMMSS/` 截图目录。
- **VALIDATE**: `git diff --check`

### UPDATE `INTERFACES.md`

- **IMPLEMENT**: 在 Browser to Backend 增加 skill 列表接口；在 task message 接口说明可选 `skills` 字段；说明后端只返回 name/description，不返回路径/正文。
- **PATTERN**: 当前接口文档按边界分层，不写低层实现细节。
- **IMPORTS**: 无。
- **GOTCHA**: 不要把完整 schema 或实现代码复制进文档。
- **VALIDATE**: `git diff --check`

### UPDATE `asset/deepagents_platform_knowledge_pack.md`

- **IMPLEMENT**: 更新 Business Rules / Input And Output Examples / Related Code Paths / Known Pitfalls：记录 `/api/skills` 只投影 `backend/skills`、浏览器不可见 path/body、composer chip 通过 `MessageRequest.skills` 进入后端并格式化为 message mention。
- **PATTERN**: 该知识包已有 Skills、API routes、Frontend model picker、Browser E2E 条目。
- **IMPORTS**: 无。
- **GOTCHA**: 只写稳定业务规则和运行边界，不写一次性排障时间线。
- **VALIDATE**: `git diff --check`

---

## 测试策略

### 单元测试

- 后端 `backend/tests/unit/skills/test_project_skills.py`
  - 项目 skill 列表来自 `backend/skills`。
  - 输出不含 path/body。
  - message formatting 稳定。
- 后端 `backend/tests/unit/api/test_skills.py`
  - `GET /api/skills` 成功、鉴权、默认 skills。
- 后端 `backend/tests/unit/api/test_tasks.py`
  - `skills` 字段有效时消息被标记。
  - 未知 skill 在 start_run 前 400。
- 前端 `frontend/tests/state/test_skill_selection.test.ts`
  - normalize/filter/slash trigger/replace/dedupe。
- 前端现有 state/workspace tests
  - payload 包含 skills。
  - hook/component/CSS 边界没有漂移。

### 集成测试

- 后端 API 集成：`GET /api/skills` + `POST /api/tasks/{id}/messages` 带 skills，验证返回 task state 中用户 message content。
- 前端集成：`useTaskWorkspace()` 加载 skills，`ChatComposer` 选择后通过 `postTaskMessage()` 提交。

### 浏览器 E2E

- 新增 `frontend/e2e-playwright/test_skill_selector.spec.mjs`。
- 必须基于实际前后端服务，默认复用用户已运行的 `3001` 和 `8001`。
- 截图保存在 `frontend/e2e-playwright/e2e-YYYYMMDDHHMMSS/skill-selector/`，不提交 git。

### 边界情况

- `backend/skills` 为空：`GET /api/skills` 返回 `[]`，前端输入 `/` 显示空状态。
- skill 缺少 frontmatter/name：跳过，不 500。
- duplicate skill name：沿用 loader 保留第一个。
- API 返回非数组/网络失败：前端聊天可继续使用，显示轻量 warning。
- 输入 `/` 后 Escape/外部点击关闭，不丢 input。
- 输入 `/web` 选择后替换触发 token，不追加重复文本。
- 运行中任务：不打开 picker，不允许通过 skill 选择绕过禁用。
- 发送失败：保留 input 和 selected skill chips。
- path/body 泄露：前后端测试和 E2E 都断言不出现 `SKILL.md`、`/mnt/`、`backend/skills`。
- 移动端：chip/menu 不遮挡上传、模型选择、发送按钮。

---

## 验证命令

执行所有命令，确保零回归与功能 100% 正确。

### 级别 1：语法与风格

```bash
cd /mnt/d/AgentProject/MyAgent/backend
uv run ruff check .
uv run mypy app tests
```

```bash
cd /mnt/d/AgentProject/MyAgent/frontend
npm run typecheck
npm run lint
```

### 级别 2：单元测试

```bash
cd /mnt/d/AgentProject/MyAgent/backend
uv run pytest tests/unit/skills/test_loader.py tests/unit/skills/test_project_skills.py tests/unit/api/test_skills.py tests/unit/api/test_tasks.py
```

```bash
cd /mnt/d/AgentProject/MyAgent/frontend
npm test
```

### 级别 3：集成测试

```bash
cd /mnt/d/AgentProject/MyAgent/backend
uv run pytest tests
```

```bash
cd /mnt/d/AgentProject/MyAgent/frontend
npm run build
```

### 级别 4：手动验证

```bash
curl -s http://127.0.0.1:8001/api/skills
```

期望只看到类似：

```json
[
  {"name":"code-review","description":"..."},
  {"name":"web-research","description":"..."}
]
```

并确认响应中没有 `path`、`SKILL.md`、`/mnt/`、`backend/skills`、skill 正文。

手动浏览器步骤：

- 打开 `http://127.0.0.1:3001/`。
- 点击输入框，输入 `/`，看到 `code-review` 和 `web-research`。
- 输入 `/web`，只剩 `web-research`。
- 点击 `web-research`，看到 chip，textarea 中 `/web` 被移除。
- 继续输入“搜索今天的 AI 新闻”，发送。
- 用户消息显示 skill 引用和正文。

### 级别 5：浏览器 E2E

```bash
cd /mnt/d/AgentProject/MyAgent/frontend
MYAGENT_E2E_BASE_URL=http://127.0.0.1:3001 \
MYAGENT_E2E_API_URL=http://127.0.0.1:8001 \
MYAGENT_E2E_EVIDENCE_DIR=./e2e-playwright/e2e-$(date +%Y%m%d%H%M%S)/skill-selector \
npx playwright test e2e-playwright/test_skill_selector.spec.mjs --reporter=line
```

如改动影响通用 runtime contract，再运行：

```bash
cd /mnt/d/AgentProject/MyAgent/frontend
npm run e2e:runtime-contracts
```

### 级别 6：文档和空白

```bash
cd /mnt/d/AgentProject/MyAgent
git diff --check
```

---

## 验收标准

- [ ] `GET /api/skills` 只返回 `backend/skills` 下的可用 skill。
- [ ] skill API 响应只包含 `name` 和 `description`，不包含路径、正文、环境变量或敏感信息。
- [ ] 输入 `/` 后 skill 选择列表显示在 composer 附近。
- [ ] 输入 `/关键词` 后列表按 name/description 筛选。
- [ ] 点击或键盘选择 skill 后，composer 内显示 Codex 风格 chip。
- [ ] 选择 skill 后 `/query` 触发文本被替换/移除，不重复追加。
- [ ] 用户可以删除 chip。
- [ ] 选择 skill 不会自动创建任务、上传文件或发送消息。
- [ ] 发送时 selected skills 通过结构化字段到达后端，并被格式化进用户消息。
- [ ] 发送成功后 input 和 selected skill chips 清空。
- [ ] 发送失败后 input 和 selected skill chips 保留。
- [ ] 上传、模型选择、发送、停止任务和历史会话行为无回归。
- [ ] 后端 pytest、ruff、mypy 全通过。
- [ ] 前端 typecheck、test、lint、build 全通过。
- [ ] 真实浏览器 E2E 通过，并保存截图证据到 ignored evidence 目录。
- [ ] `INTERFACES.md` 和 `asset/deepagents_platform_knowledge_pack.md` 已同步。

---

## 完成检查清单

- [ ] 所有任务均已按顺序完成。
- [ ] 每个任务的验证都已立即通过。
- [ ] 所有验证命令都已成功执行。
- [ ] 完整测试套件通过（后端 + 前端）。
- [ ] 无 lint 或类型检查错误。
- [ ] 手动测试确认功能可用。
- [ ] 浏览器 E2E 截图证据已生成且未提交。
- [ ] 验收标准全部满足。
- [ ] 已完成代码质量与可维护性审查。
- [ ] 未暴露本地 skill 路径、skill 正文、provider key、access token 或客户资料。

---

## 备注

- 信心分数：8/10。主要风险在 composer 的键盘/IME/focus 细节，以及 E2E 发送路径是否需要真实模型可用。后端 skill API 和 message formatting 风险低。
- 第一版建议不做 contenteditable。textarea 内无法真正渲染 inline chip；用 composer 内 chip shelf 可以满足用户可见 chip，同时避免重写输入法和 selection。
- 如果后续需要像 Codex 一样 chip 出现在文字流内部，再单独设计 rich composer，不要在本任务中顺手重构。
- 不要把 `.agents/skills`、Codex 全局 skills、`MYAGENT_SKILLS_DIRS` 或用户主目录 skill 暴露给前端。
