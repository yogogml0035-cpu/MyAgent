---
name: ralph
description: "将 tasks/<requirement-slug> 需求工作区或其中的 PRD、计划、需求说明转换为 prd.json 格式，供 Ralph 自主 agent 系统使用。当你需要把任务目录中的当前需求内容转换为 Ralph 的 JSON 格式时使用。触发词：将prd 转成 prd.json"
---

# Ralph PRD Converter

将任务工作区中的当前需求内容转换为 Ralph 用于自主执行的 prd.json 格式。

---

## 工作流程

获取显式传入的 `tasks/<requirement-slug>` 需求工作区或其中的需求源文件，并将其转换为同一需求目录中的 `prd.json`。

允许的输入形式：

```text
tasks/<requirement-slug>
tasks/<requirement-slug>/prd.md
tasks/<requirement-slug>/requirements.md
tasks/<requirement-slug>/plan.md
tasks/<requirement-slug>/<other-source-file>
```

规则：

- 支持相对路径、绝对路径、`/` 和 `\`。如果没有提供任何 `tasks/<requirement-slug>` 路径，不要从仓库中猜测最近任务，直接报错并要求用户提供任务目录或任务源文件。
- 先解析用户显式提供的路径，并定位到对应的 `tasks/<requirement-slug>/` 工作区。
- 如果输入是任务目录，读取该目录顶层的当前需求正文与相关说明文件作为参考；不要默认读取 `history/`、`logs/`、`screenshots/` 等历史或执行痕迹。
- 如果输入是具体源文件，优先参考用户指定的文件；如果信息不足，自行在同一任务目录、当前代码库和相关文档中补足上下文，不要立刻询问用户。
- 如果同时传入多个源文件，它们必须位于同一个 `tasks/<requirement-slug>/` 目录；否则直接报错。
- 如果用户显式传入 `prd.json`，说明这是本 skill 的目标产物而不是输入参考，直接报错并要求改传任务目录或需求源文件。
- 如果任务目录中缺少可用的当前需求正文或说明内容，明确指出缺少相关内容，并说明已检查的路径。
- 如果用户本轮自然语言补充与任务目录中的当前内容冲突，明确列出冲突点，不要静默选择一边。
- 输出永远写入解析出的任务目录中的 `prd.json`。
- `branchName` 必须从需求目录名派生，例如 `tasks/login-fix-error/` -> `ralph/login-fix-error`。

---

## 输出格式

```json
{
  "project": "[Project Name]",
  "branchName": "ralph/[feature-name-kebab-case]",
  "description": "[Feature description from PRD title/intro]",
  "userStories": [
    {
      "id": "US-001",
      "title": "[Story title]",
      "description": "As a [user], I want [feature] so that [benefit]",
      "acceptanceCriteria": [
        "Criterion 1",
        "Criterion 2",
        "Typecheck passes"
      ],
      "priority": 1,
      "passes": false,
      "notes": "",
      "retryCount": 0,
      "blocked": false
    }
  ]
}
```

---

## Story 大小：第一规则

**每个 story 必须能在一次 Ralph 迭代（一个 context window）中完成。**

Ralph 每次迭代都会生成一个新的 Claude code 或者 Codex 实例，没有之前工作的记忆。如果 story 太大，LLM 在完成之前会用完 context，并产生损坏的代码。

### 合适大小的 stories：
- 添加 database 列和 migration
- 向现有页面添加 UI component
- 使用新逻辑更新 server action
- 向列表添加 filter dropdown

### 太大（需要拆分）：
- "构建整个 dashboard" - 拆分为：schema、queries、UI components、filters
- "添加 authentication" - 拆分为：schema、middleware、login UI、session handling
- "重构 API" - 拆分为每个 endpoint 或 pattern 一个 story

**经验法则：** 如果你无法用 2-3 句话描述这个变更，那就太大了。

---

## Story 排序：依赖优先

Stories 按 priority 顺序执行。较早的 stories 不能依赖于较晚的。

**正确顺序：**
1. Schema/database 变更（migrations）
2. Server actions / backend logic
3. 使用 backend 的 UI components
4. 聚合数据的 Dashboard/summary views

**错误顺序：**
1. UI component（依赖于尚不存在的 schema）
2. Schema 变更

---

## Acceptance Criteria：必须可验证

每个标准必须是 Ralph 可以检查的内容，而不是模糊的内容。

### 好的标准（可验证）：
- "向 tasks 表添加 `status` 列，默认值为 'pending'"
- "Filter dropdown 有选项：All、Active、Completed"
- "点击删除显示确认对话框"
- "Typecheck 通过"
- "Tests 通过"

### 不好的标准（模糊）：
- "工作正常"
- "用户可以轻松执行 X"
- "良好的 UX"
- "处理边缘情况"

### 始终作为最终标准包含：
```
"Typecheck passes"
```

对于具有可测试逻辑的 stories，还应包含：
```
"Tests pass"
```

### 对于更改 UI 的 stories，还应包含：
```
"Verify in browser using Playwright"
```

Frontend stories 在视觉验证之前不算完成。Ralph 将使用 Playwright 导航到页面，与 UI 交互，并确认更改有效。

### 不要保留泛化的浏览器标准

如果输入 PRD 里出现下面这种标准：

- "Verify in browser using Playwright"
- "在浏览器中验证"
- "验证页面正常工作"

转换成 `prd.json` 时，不要原样照搬。必须扩写成 validator 真能执行的断言。

例如不要写：

```json
"Verify in browser using Playwright"
```

要改写成类似：

```json
"Use Playwright to open /login and submit valid credentials",
"A token is stored in localStorage after successful login",
"The page redirects to ?subdomain=user and protected content is visible"
```

### 认证、支付、上传、导入导出、多步表单必须写闭环

如果 story 属于高风险用户流程，必须把验收标准写成完整闭环，而不是单点动作。

最低要求：

- 成功路径可真实跑通
- 关键运行时状态可观察
- 页面或接口结果可观察
- 刷新后状态是否保持可观察
- 失败路径至少有一个明确断言

认证类最低模板：

```json
[
  "Register a new unique account successfully",
  "Log in with the newly registered account successfully",
  "Store the auth token in localStorage after login",
  "Redirect to the correct protected portal based on primaryIdentity",
  "Restore the logged-in state after a page refresh",
  "Show a clear error message for invalid credentials"
]
```

### 前后端集成必须验证运行时可达

只要 story 涉及前端调用后端，就不能只写“改成调用新接口”。

必须补至少一条运行时标准：

- 请求在本地开发环境中真实到达目标后端接口
- 不是打到前端 dev server 自己的假路径
- 成功和失败结果都能在 UI 上观察到

如果 PRD 中缺了这层约束，转换时主动补上。

---

## 转换规则

1. **每个 user story 成为一个 JSON 条目**
2. **IDs**：顺序（US-001、US-002 等）
3. **Priority**：基于依赖顺序，然后是文档顺序
4. **所有 stories**：`passes: false`、空的 `notes`、`retryCount: 0`、`blocked: false`
5. **branchName**：从需求目录名派生，前缀为 `ralph/`
6. **始终添加**："Typecheck passes" 到每个 story 的 acceptance criteria

### 转换时的增强规则

1. 如果原 PRD 的 acceptance criteria 过于抽象，主动重写成可执行断言
2. 如果某个 UI story 依赖 dev proxy、env、base URL、gateway、seed data 才能成立，而原 PRD 没拆，主动增加前置 story
3. 如果多个 story 合起来才构成一个真实用户流程，主动增加最后一个“闭环集成验证” story
4. 不要让“调用接口”“保存 token”“完成接入”这种实现描述直接进入最终 `prd.json`
5. 优先写 validator 可以用代码检查、curl、Playwright、localStorage、URL、页面文案、截图来确认的标准

---

## 拆分大型 PRD

如果 PRD 有大型功能，请拆分它们：

**原始：**
> "添加用户通知系统"

**拆分为：**
1. US-001: 向 database 添加 notifications 表
2. US-002: 创建用于发送通知的 notification service
3. US-003: 向 header 添加 notification bell 图标
4. US-004: 创建 notification dropdown panel
5. US-005: 添加 mark-as-read 功能
6. US-006: 添加 notification preferences 页面
7. US-007: 使用浏览器验证通知创建到展示的完整闭环

每个都是一个可以独立完成和验证的专注变更。

### 对认证和账号体系的拆分规则

不要只拆成：

1. HTTP client
2. AuthContext
3. Login page

这还不够。

至少应拆成：

1. 前端到后端的认证请求链路可达
2. 注册接口接入
3. 登录接口接入
4. 登录态恢复与退出
5. 注册→登录→进入受保护页面→刷新恢复登录态的闭环验证

最后一个 story 很关键。没有它，Ralph 很容易把“代码接上了”误判成“功能完成了”。

---

## 示例

**输入 PRD：**
```markdown
# Task Status Feature

Add ability to mark tasks with different statuses.

## Requirements
- Toggle between pending/in-progress/done on task list
- Filter list by status
- Show status badge on each task
- Persist status in database
```

**输出 prd.json：**
```json
{
  "project": "任务应用",
  "branchName": "ralph/task-status",
  "description": "任务状态功能 - 使用状态指示器跟踪任务进度",
  "userStories": [
    {
      "id": "US-001",
      "title": "向任务表添加状态字段",
      "description": "作为开发者，我需要在数据库中存储任务状态。",
      "acceptanceCriteria": [
        "添加 status 列：'pending' | 'in_progress' | 'done' (默认 'pending')",
        "成功生成并运行 migration",
        "Typecheck 通过"
      ],
      "priority": 1,
      "passes": false,
      "notes": "",
      "retryCount": 0,
      "blocked": false
    },
    {
      "id": "US-002",
      "title": "在任务卡片上显示状态徽章",
      "description": "作为用户，我想一眼看到任务状态。",
      "acceptanceCriteria": [
        "每个任务卡片显示彩色状态徽章",
        "徽章颜色：灰色=pending，蓝色=in_progress，绿色=done",
        "Typecheck 通过",
        "Use Playwright to open the task list page and confirm every visible task card shows a status badge",
        "No console errors are present on the page"
      ],
      "priority": 2,
      "passes": false,
      "notes": "",
      "retryCount": 0,
      "blocked": false
    },
    {
      "id": "US-003",
      "title": "向任务列表行添加状态切换",
      "description": "作为用户，我想直接从列表更改任务状态。",
      "acceptanceCriteria": [
        "每行有状态下拉菜单或切换按钮",
        "更改状态后立即保存",
        "UI 更新无需刷新页面",
        "Typecheck 通过",
        "Use Playwright to change a task status from the list view and confirm the badge updates immediately",
        "Refresh the page and confirm the updated status persists"
      ],
      "priority": 3,
      "passes": false,
      "notes": "",
      "retryCount": 0,
      "blocked": false
    },
    {
      "id": "US-004",
      "title": "按状态过滤任务",
      "description": "作为用户，我想过滤列表以仅查看特定状态。",
      "acceptanceCriteria": [
        "过滤下拉菜单：All | Pending | In Progress | Done",
        "过滤状态持久化在 URL params 中",
        "Typecheck 通过",
        "Use Playwright to switch the filter and confirm only matching tasks remain visible",
        "Refresh the page and confirm the selected filter is restored from the URL params"
      ],
      "priority": 4,
      "passes": false,
      "notes": "",
      "retryCount": 0,
      "blocked": false
    }
  ]
}
```

---

## 需求目录产物规则

`prd.json` 必须与源 PRD 位于同一个需求目录：

```text
tasks/<requirement-slug>/
  prd.md
  plan.md
  prd.json
  progress.txt
  screenshots/
  logs/
  history/
```

## 重新生成 prd.json 前的快照

如果目标目录中已经存在 `prd.json`，重新生成表示开启新的 Ralph 执行轮次。写入新的 `prd.json` 之前，必须先创建完整快照：

```text
tasks/<requirement-slug>/history/YYYY-MM-DD-HHMMSS/
  prd.md          # 如存在
  plan.md         # 如存在
  prd.json        # 如存在
  progress.txt    # 如存在
  screenshots/    # 如存在，完整复制
  logs/           # 如存在，完整复制
```

快照后：

- 写入新的 `prd.json`
- 所有 stories 的执行状态从头开始：`passes: false`、`notes: ""`、`retryCount: 0`、`blocked: false`
- 清空并重建 `progress.txt`、`screenshots/`、`logs/`
- `progress.txt` 写入初始 header：

```markdown
# Ralph Progress

Requirement: tasks/<requirement-slug>
Started: YYYY-MM-DD HH:mm
Source: prd.json

## Codebase Patterns
```

追加 `progress.txt`、新增截图、写日志、或更新 `prd.json` 中的执行状态字段不触发快照。

---

## 保存前检查清单

在编写 prd.json 之前，验证：

- [ ] 输入已解析为本机存在的 `tasks/<requirement-slug>/` 工作区或同目录需求源文件
- [ ] 已读取任务目录中的当前需求正文；未把 `history/`、`logs/`、`screenshots/` 当作默认参考
- [ ] 如目标 `prd.json` 已存在，已先创建完整 `history/YYYY-MM-DD-HHMMSS/` 快照
- [ ] 每个 story 可以在一次迭代中完成（足够小）
- [ ] Stories 按依赖顺序排序（schema 到 backend 到 UI）
- [ ] 每个 story 都有 "Typecheck passes" 作为标准
- [ ] UI stories 的浏览器标准已经展开为页面、操作、期望结果，而不是一句泛化短语
- [ ] 认证/支付/上传/多步流程 stories 有真实闭环标准
- [ ] 前后端集成 stories 包含运行时可达验证
- [ ] 复杂功能最后有一个闭环集成验证 story
- [ ] Acceptance criteria 是可验证的（不模糊）
- [ ] 没有 story 依赖于后面的 story
- [ ] 每个 story 包含 `retryCount: 0` 和 `blocked: false` 字段

---

## 写入后：JSON 自动修复与验证（必须执行）

**每次写入 prd.json 之后，必须立即运行修复脚本**，以防止 LLM 输出中的未转义引号、多余逗号等问题导致解析失败。

### 执行步骤

```bash
python3 .agents/skills/ralph/scripts/repair_prd_json.py tasks/<requirement-slug>/prd.json
```

脚本必须接收当前需求目录中的 `prd.json` 路径：

```bash
python3 .agents/skills/ralph/scripts/repair_prd_json.py tasks/login/prd.json
```

脚本会自动安装 `json-repair`（若未安装），修复文件后覆盖写回，并打印结果。

### 脚本位置

`.agents/skills/ralph/scripts/repair_prd_json.py`

### 说明

- `json-repair` 自动修复 LLM 生成 JSON 的常见问题：未转义内嵌双引号、多余逗号、括号不匹配等
- `ensure_ascii=False` 保留中文字符，不转成 `\uXXXX` 转义序列
- 修复后再做一次 `json.loads()` 二次验证，确保结果绝对合法
- 修复失败则报错退出，不覆盖原文件
