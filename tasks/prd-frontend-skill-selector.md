# PRD: Frontend Skill Selector

## Introduction

为 MyAgent 聊天输入框增加当前项目 skill 选择能力。用户在输入框输入 `/` 后，可以看到 `backend/skills` 下所有可用 skill，按关键词筛选，并像 Codex 一样点击生成 skill chip。这样用户无需记忆 skill 名称，也不会误选本机其他全局 skill。

## Goals

- 用户输入 `/` 后能在聊天输入框附近看到当前项目 `backend/skills` 下的所有可用 skill。
- 用户可以通过 skill 名称或描述筛选列表，并用鼠标或键盘选择。
- 选中 skill 后，输入框中出现 Codex 风格 chip，焦点回到输入框，用户可以继续输入需求。
- skill 选择不自动发送消息；只有用户点击发送或按发送快捷键后才进入现有任务流程。
- 浏览器端不展示本地 skill 文件路径、环境变量或其他敏感运行信息。

## User Stories

### US-001: 当前项目 Skill 列表可被前端读取
**描述：** 作为用户，我想让前端只读取当前项目 `backend/skills` 下的 skill，以便选择列表不会混入 Codex 全局 skill 或本机其他私有 skill。

**Acceptance Criteria：**
- [ ] 在本地开发环境中，前端发出的 skill 列表请求可以真实到达后端并返回成功响应。
- [ ] 默认项目中存在 `backend/skills/code_review/SKILL.md` 和 `backend/skills/web_research/SKILL.md` 时，响应中包含 `code-review` 和 `web-research` 的名称与描述。
- [ ] 响应中不包含 skill 本地文件路径、目录路径、环境变量或 skill 正文。
- [ ] 后端只扫描 `backend/skills` 下的可用 skill，不返回 Codex 全局 skill、`.agents/skills` 或用户主目录下的 skill。
- [ ] 当 `backend/skills` 下没有可用 skill 时，响应为空列表且不是 500 错误。
- [ ] 后端测试通过，且 `uv run ruff check .` 和 `uv run mypy app tests` 通过。

### US-002: 输入 `/` 展示 Skill 选择列表
**描述：** 作为用户，我想在聊天输入框输入 `/` 后看到所有可选 skill，以便快速发现可用能力。

**Acceptance Criteria：**
- [ ] 使用 agent-browser 打开 `http://127.0.0.1:3001/`，点击聊天输入框并输入 `/` 后，页面在输入框附近显示 skill 选择列表。
- [ ] 列表中每一项都显示 skill 名称和简介，名称可完整识别，简介过长时不会撑破容器。
- [ ] 输入 `/web` 后，列表只显示名称或简介匹配 `web` 的 skill；输入 `/code` 后，列表只显示匹配 `code` 的 skill。
- [ ] 无匹配结果时，列表显示轻量空状态，输入框仍可继续编辑。
- [ ] 按 `Escape` 或点击选择器外部后，skill 列表关闭且输入框内容不丢失。
- [ ] 页面无控制台错误，移动端和桌面端文本不重叠、不溢出。
- [ ] 前端 `npm run typecheck`、`npm test` 和 `npm run lint` 通过。

### US-003: 选择 Skill 后生成 Codex 风格 Chip
**描述：** 作为用户，我想点击 skill 后在输入框中看到一个类似 Codex 的 skill chip，以便明确知道本轮消息已引用该 skill。

**Acceptance Criteria：**
- [ ] 使用 agent-browser 打开 `http://127.0.0.1:3001/`，输入 `/` 并点击 `web-research` 后，输入框中出现一个可识别的 `web-research` skill chip。
- [ ] 如果用户先输入 `/web` 再选择 `web-research`，chip 替换 `/web` 这段触发文本，而不是追加重复文本。
- [ ] chip 出现后输入焦点回到输入框，用户可以继续输入自然语言需求。
- [ ] chip 视觉上与普通正文不同，包含 skill 图标或等价标记、skill 名称，并保持当前暖色画布和珊瑚主色体系。
- [ ] 用户可以删除已插入的 skill chip；删除后待发送内容中不再包含该 skill 引用。
- [ ] 选择 skill 不会自动创建任务、上传文件或发送消息。
- [ ] 页面无控制台错误，移动端和桌面端 chip 不遮挡上传、模型选择、发送和停止按钮。

### US-004: Skill Chip 与用户正文一起发送
**描述：** 作为用户，我想选择 skill 后继续输入需求并发送，以便后端收到的本轮消息能表达“使用这个 skill 处理该需求”。

**Acceptance Criteria：**
- [ ] 用户选择 `code-review` chip，继续输入“检查最近改动”，点击发送后，用户消息卡片中能看到该 skill 引用和正文。
- [ ] 发送前选中的 skill 引用随消息内容一起提交，后端接收到的消息可以区分出用户选择的 skill 名称。
- [ ] 发送成功后输入框清空，skill chip 也被清空。
- [ ] 发送失败时，输入框保留用户正文和已选择的 skill chip，方便用户重试。
- [ ] 当前任务运行中时，输入框仍保持现有“回复生成中，请稍候...”体验，不允许通过 skill 选择绕过运行中限制。
- [ ] 上传文件、模型选择、发送、停止任务和会话历史功能仍按现有行为可用。

### US-005: Skill 选择完整闭环浏览器验收
**描述：** 作为用户，我想从打开页面到选择 skill、补充需求、发送消息完成一条真实路径，以便确认功能不是孤立控件。

**Acceptance Criteria：**
- [ ] 基于实际前后端服务运行浏览器 E2E，不使用静态 mock 页面替代。
- [ ] 使用 agent-browser 打开 `http://127.0.0.1:3001/`，输入 `/` 后能看到 `code-review` 和 `web-research`。
- [ ] 选择 `web-research` 后出现 skill chip，继续输入“搜索今天的 AI 新闻”，点击发送。
- [ ] 页面出现新的用户消息，消息中包含 `web-research` 引用和“搜索今天的 AI 新闻”正文。
- [ ] 截图证据保存到 `frontend/e2e-playwright/e2e-YYYYMMDDHHMMSS/`，截图目录不提交 git。
- [ ] 浏览器控制台无错误；前端 `npm run build` 通过。

## Functional Requirements

- FR-1: 系统必须只展示当前项目 `backend/skills` 下可用的 skill。
- FR-2: 系统必须从 `SKILL.md` frontmatter 中读取 skill 名称和描述，并只把名称、描述返回给前端。
- FR-3: 系统不得向浏览器返回 skill 本地路径、skill 正文、环境变量或其他敏感运行信息。
- FR-4: 用户在聊天输入框中输入 `/` 时，系统必须显示 skill 选择列表。
- FR-5: 用户在 `/` 后输入关键词时，系统必须按 skill 名称和描述过滤列表。
- FR-6: 用户可以通过鼠标点击选择 skill。
- FR-7: 用户可以通过键盘在列表中移动选择、确认选择和关闭列表。
- FR-8: 用户选择 skill 后，输入框必须显示 Codex 风格 chip，而不是只显示普通文本。
- FR-9: 用户选择 skill 后，输入焦点必须回到输入框，允许继续输入需求。
- FR-10: 用户删除 chip 后，待发送消息中不得继续包含该 skill 引用。
- FR-11: skill 选择不得自动创建任务、上传文件或发送消息。
- FR-12: 发送成功后，输入框正文和已选 skill chip 必须一起清空。
- FR-13: 发送失败后，输入框正文和已选 skill chip 必须保留，方便用户重试。
- FR-14: skill 选择器不得破坏现有上传文件、模型选择、发送、停止任务和历史会话操作。

## Non-Goals

- 不展示 Codex 全局 skill、`.agents/skills` 或用户主目录中的 skill。
- 不支持在浏览器内创建、编辑、删除或保存 skill。
- 不支持 skill 版本管理、skill 正文预览或 skill 路径跳转。
- 不改变后端现有 DeepAgents skill 加载和任务运行语义，除非发送消息时需要保留用户选择的 skill 引用。
- 不新增用户账号、权限系统或多用户 skill 可见性规则。

## Design Considerations

- Skill 选择器视觉参考 Codex 的 slash skill 选择体验：列表贴近输入框，选中后显示 compact chip。
- 视觉必须保持 MyAgent 当前暖色画布、珊瑚主色、克制圆角和密集工作台布局。
- chip 应该清晰区别于普通正文，但不能遮挡输入框、上传按钮、模型选择器或发送按钮。
- 列表项应优先展示 skill 名称，其次展示简介；简介过长时截断或换行，但不得造成布局跳动。
- 空会话和已有对话两种 composer 位置都必须可用。

## Technical Considerations

- 现有后端已有 `backend/app/skills/loader.py`，可以复用其 `SKILL.md` frontmatter 解析能力，但前端可见范围必须限定为 `backend/skills`。
- 现有前端输入区集中在 `frontend/components/chat/ChatComposer.tsx`，输入状态由 `frontend/hooks/use-task-workspace.ts` 管理。
- 新前端 API 调用应放在 `frontend/lib/task-api.ts`，后端字段归一化应集中在 `frontend/app/task-state.ts` 或相邻纯 helper 中。
- 行为和视觉变更需要补充前端 Node 测试、真实浏览器 E2E 和截图证据。
- 如果需要向后端传递 skill 选择，应保证后端能从消息中可靠识别 skill 名称，同时不要求浏览器知道 skill 文件路径。

## Success Metrics

- 用户在 2 次操作内完成 skill 选择：输入 `/`，点击目标 skill。
- 默认项目 skill 列表中 100% 包含 `backend/skills` 下的可用 skill，且 0 个 Codex 全局 skill 混入。
- skill 选择后继续输入和发送的主流程无回归。
- 桌面端和移动端浏览器验收均无文本重叠、无控制台错误。

## Open Questions

- 无。
