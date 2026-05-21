# PRD: 多会话并行与 Thinking 审计

## Introduction

当前 MyAgent 需要支持不同会话真正并行处理任务，同时保持同一会话内的运行互斥，避免上下文、工具调用顺序和 reasoning 回传被打乱。对于 DeepSeek 等 thinking 模型，工具调用后的后续 provider 请求必须带回 `reasoning_content`，否则会触发 400 错误。因此，本功能要求在每个 task/run 内保存完整、可审计、互不污染的运行事件流，并在前端默认保持简洁进度展示，展开诊断时可查看完整证据。

`reasoning_content` 属于高敏运行证据，必须限定在当前 run 的诊断日志中使用，不进入长期记忆、普通聊天消息或默认产物。

## Goals

- 支持不同会话同时运行任务，且各自状态、日志、工具调用、推理内容和最终答案按 task/run 隔离。
- 保持同一会话运行中不可重复发送或排队到同一上下文。
- 修复 thinking 模型在工具调用后的 `reasoning_content` 回传链路，避免因缺失字段导致 provider 返回 400。
- 为新 run 保存完整可审计事件流，包括 `reasoning_content`、answer delta、tool call、tool result、状态更新、错误和最终答案。
- 前端默认只展示简约进度，展开日志或复制诊断时能追溯 provider 与工具链路细节。
- 支持同一会话后续切换 thinking/non-thinking 模型，并按当前模型兼容方式回放上下文。

## User Stories

### US-001: 不同会话并行运行

**描述：** 作为用户，我想在会话 A 运行中切到会话 B 发起另一个任务，以便多个独立任务可以同时推进。

**Acceptance Criteria：**

- [ ] 当会话 A 已处于运行中时，用户可以在不同会话 B 发起新任务，B 不需要等待 A 完成。
- [ ] A/B 两个 run 都有各自独立的 `session_id`、`task_id` 或 `run_id`，状态更新只写入对应 run。
- [ ] A/B 的日志、工具调用、`reasoning_content` 和最终答案不会互相出现在对方会话或 run 中。
- [ ] A/B 中任一 run 失败时，另一个正在运行的 run 仍保持自己的状态并继续运行或独立失败。
- [ ] 在本地实际前后端服务中，同时启动两个不同会话，两个会话都能独立运行到完成或独立失败。
- [ ] 相关后端并发和状态隔离测试通过。
- [ ] 相关前端任务状态和会话切换测试通过。

### US-002: 同一会话运行中保持互斥

**描述：** 作为用户，我想在同一会话已有任务运行时看到明确的发送保护，以便不会把同一上下文的消息、工具结果和 reasoning 回传顺序打乱。

**Acceptance Criteria：**

- [ ] 当同一会话已有 run 处于运行中时，用户不能在该会话再次发送新消息或创建第二个排队 run。
- [ ] 同一会话重复发送被阻止时，系统不会创建新的 run、不会追加待执行消息、不会改变当前 run 的上下文顺序。
- [ ] 当前 run 完成或失败后，该会话恢复可发送状态。
- [ ] 前端在同一会话运行中展示不可发送状态或等价保护，用户能明确知道当前任务仍在运行。
- [ ] 使用 agent-browser 打开本地前端，进入同一会话运行中再次尝试发送，页面保持发送保护且无控制台错误。

### US-003: Thinking 模型工具调用后的 `reasoning_content` 正确回传

**描述：** 作为使用 thinking 模型的用户，我希望工具调用后的后续模型请求自动携带必要的 `reasoning_content`，以便任务不会因为 provider 要求缺失而失败。

**Acceptance Criteria：**

- [ ] thinking 模型在生成工具调用前后产生的 `reasoning_content` 会被当前 run 捕获并保留。
- [ ] 同一 run 内工具结果返回后，下一次 provider 请求包含该 provider 要求回传的 `reasoning_content`。
- [ ] 使用模拟或真实 DeepSeek-compatible thinking provider 的工具调用场景时，不再出现 `The reasoning_content in the thinking mode must be passed back to the API` 这类 400 失败。
- [ ] `reasoning_content` 的保存和回放按当前 run 隔离，不会进入其他 session、task 或 run。
- [ ] 同一会话后续切换到 non-thinking 模型时，上下文回放不会向不兼容模型发送 thinking 专属字段。
- [ ] 同一会话后续切回 thinking 模型时，上下文回放按当前 provider 兼容规则处理，不伪造旧 run 缺失的 `reasoning_content`。
- [ ] 相关 provider adapter、工具调用和模型切换测试覆盖成功路径与缺失数据路径。

### US-004: 新 run 保存完整可审计事件流

**描述：** 作为开发者或排障人员，我想按 task/run 查看完整事件证据，以便定位 provider、工具链路、状态转换或最终答案问题。

**Acceptance Criteria：**

- [ ] 新 run 的事件流至少记录：`reasoning_content`、answer delta、tool call、tool result、状态更新、错误和最终答案。
- [ ] 每条事件包含可排序的顺序信息、时间信息、事件类型以及归属的 session/task/run 标识。
- [ ] 按单个 run 查询事件时，只返回该 run 的事件，不包含其他会话或其他 run 的内容。
- [ ] `reasoning_content` 完整保存在当前 run 的诊断日志中，展开诊断时可完整查看。
- [ ] `reasoning_content` 不进入长期记忆、普通聊天消息正文或默认产物下载。
- [ ] 旧失败 run 不补数据；历史缺失字段在界面或诊断中只能显示为不可用，不允许伪造补齐。
- [ ] 相关存储、查询、事件顺序和隔离测试通过。

### US-005: 前端默认简洁进度与展开诊断

**描述：** 作为用户，我想默认看到简单清晰的运行进度，并在需要排查时展开完整诊断，以便日常使用不被复杂日志打扰，排障时又有足够证据。

**Acceptance Criteria：**

- [ ] 默认前端日志只显示简约状态，例如“AI 正在思考 / 生成 / 调用工具 / 工具返回 / 完成 / 失败”。
- [ ] 展开单个 run 的日志后，可以看到该 run 的详细事件证据，包括完整 `reasoning_content`、工具参数、工具结果、错误和最终答案。
- [ ] 复制诊断内容时包含当前 run 的 provider 和工具链路细节，且不混入其他 run 的日志。
- [ ] 默认聊天消息区不会把 `reasoning_content` 当作普通 assistant 消息展示。
- [ ] 使用 agent-browser 打开本地前端，运行一个包含 thinking 与工具调用的任务，默认视图保持简洁；展开日志后能看到完整 reasoning 细节。
- [ ] 展开、收起、复制诊断过程中页面无控制台错误，文本不重叠，布局不破坏现有设计风格。

### US-006: 跨会话并行与 Thinking 审计闭环验证

**描述：** 作为项目维护者，我需要一次真实浏览器闭环验收覆盖跨会话并行、同会话互斥、thinking 工具调用和诊断日志，以便确认功能不是单点测试通过。

**Acceptance Criteria：**

- [ ] 启动本地后端 `8001` 和前端 `3001` 服务，使用实际服务而非纯 mock 页面完成验收。
- [ ] 在浏览器中创建或进入会话 A 发起长任务，再切换到会话 B 发起另一个任务，A/B 均出现独立 run 状态。
- [ ] 在会话 A 运行中尝试再次发送消息，页面保持同会话发送保护，且后端没有创建第二个同会话 run。
- [ ] 至少一个 thinking 模型工具调用场景完成后，不出现缺失 `reasoning_content` 的 400 错误。
- [ ] 展开 A/B 各自 run 日志，能看到各自完整事件流，且不会串入对方事件。
- [ ] 截图证据保存到 `frontend/e2e-playwright/e2e-YYYYMMDDHHMMSS/`，截图文件不提交 git。
- [ ] `cd backend && uv run pytest && uv run ruff check . && uv run mypy app tests` 通过。
- [ ] `cd frontend && npm run typecheck && npm test && npm run lint && npm run build` 通过。
- [ ] 相关 Playwright E2E 在实际前后端服务上通过。

## Functional Requirements

- FR-1: 系统必须允许不同会话的 run 同时处于运行中，并按 session/task/run 隔离状态、日志和最终答案。
- FR-2: 系统必须继续阻止同一会话在已有 run 运行中再次发送或排队到同一上下文。
- FR-3: 系统必须在 thinking 模型工具调用链路中捕获并保留 provider 返回的 `reasoning_content`。
- FR-4: 系统必须在同一 thinking run 的后续 provider 请求中按 provider 要求回传必要的 `reasoning_content`。
- FR-5: 系统必须在模型切换时按当前模型兼容性构造上下文，不能向 non-thinking 模型发送不兼容字段。
- FR-6: 系统必须为新 run 记录完整事件流，事件类型至少覆盖 reasoning、answer delta、tool call、tool result、状态更新、错误和最终答案。
- FR-7: 系统必须保证 run 事件查询按 task/run 隔离，并能按事件顺序重放诊断链路。
- FR-8: 系统必须保证 `reasoning_content` 只作为当前 run 的诊断日志保存和展示，不进入长期记忆、普通聊天消息或默认产物。
- FR-9: 前端默认必须展示简约进度状态，不默认暴露完整 reasoning 诊断内容。
- FR-10: 前端必须提供展开日志和复制诊断能力，诊断内容应包含当前 run 的 provider 与工具链路细节。
- FR-11: 系统不得对旧失败 run 进行伪造补数据；旧数据缺失只能显示为历史不可用。
- FR-12: 任一会话 run 失败时，系统不得改变其他正在运行会话的状态或日志归属。

## Non-Goals

- 不实现全局并发上限。
- 不实现全局任务队列。
- 不允许同一会话内并行多个 run。
- 不补齐旧失败 run 中历史缺失的 `reasoning_content`。
- 不伪造 provider 未返回或历史未保存的 reasoning 数据。
- 不把 `reasoning_content` 纳入长期记忆、普通聊天消息或默认产物。
- 不改变 provider 密钥、数据库 URL、Qdrant URL、embedding 凭据等敏感配置的存放边界。

## Design Considerations

- 默认运行日志应保持低噪音，只呈现用户可理解的简约状态。
- 详细诊断应通过展开面板、详情区域或等价交互呈现，不应挤占普通聊天回答区域。
- 涉及前端视觉和交互时必须先读取 `DESIGN.md`，延续现有暖色画布、珊瑚色主色、字体、圆角、间距和 CSS 变量。
- 诊断日志中包含高敏运行证据，界面应明确区分“普通回答”和“诊断日志”。
- 复制诊断应以当前 run 为边界，避免复制其他会话或其他 run 的内容。

## Technical Considerations

- 后端并行能力应保持本地优先和单进程运行边界，不绕过 `WEB_CONCURRENCY`、`UVICORN_WORKERS`、`GUNICORN_WORKERS` 的单进程保护。
- 并发控制应以会话互斥为核心：不同会话可并行，同一会话保持单 run。
- Postgres 仍是任务、运行、消息、事件日志和长期记忆的权威存储；SSE 只是持久化事件的投影，不是状态来源。
- 前后端字段边界保持后端 `snake_case`、前端 `camelCase`，字段转换集中在现有前端状态适配层。
- provider adapter 需要显式区分 thinking 与 non-thinking 上下文回放规则。
- 事件流需要可排序、可追溯，并能支持前端增量展示和后续诊断复制。
- 新增或调整稳定运行边界时，需要同步更新 `asset/deepagents_platform_knowledge_pack.md`。

## Success Metrics

- 两个不同会话可同时启动并独立完成或独立失败。
- thinking 模型工具调用后，缺失 `reasoning_content` 导致的 400 错误在新 run 中不再出现。
- 新 run 的诊断日志可以按 task/run 完整追溯 reasoning、工具调用、工具返回、错误和最终答案。
- 默认前端日志保持简洁，展开诊断可查看完整事件证据。
- 同一会话重复发送保护保持有效，没有新增同会话并发上下文污染。
- 后端测试、前端测试、类型检查、lint、build 和实际服务上的 Playwright E2E 均通过。

## Open Questions

- 无。
