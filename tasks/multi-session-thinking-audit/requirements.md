# Requirements: 多会话并行与 Thinking 审计

## 来源

- 生成自当前对话中的需求对齐内容。
- 关联 PRD：`prd.md`
- 外部依据：DeepSeek Thinking Mode 文档说明，thinking 模式发生 tool call 后，后续请求必须继续带回 `reasoning_content`，否则可能返回 400。参考：[DeepSeek Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode)。

## 原始对齐需求

当前需求的核心目标是支持不同会话真正并行处理任务，同时保证 thinking 模型、工具调用和运行日志在每个 task/run 内稳定、可追溯、互不污染。

需要明确的风险边界：`reasoning_content` 是高敏运行证据，完整保存和可展开查看是合理的，但应该限定在当前 run 的诊断日志里，不进入长期记忆、普通聊天消息或默认产物。

## 目标

- 支持不同会话真正并行处理任务。
- 保证 thinking 模型、工具调用和运行日志在每个 task/run 内稳定、可追溯、互不污染。
- 修复 thinking 模型并发和工具调用时的 `reasoning_content` 回传问题，避免 400。
- 新 run 保存完整可审计事件流。
- 默认前端只展示简约进度，展开日志或复制诊断时可追溯 provider 和工具链路细节，且 `reasoning_content` 完整可见。

## 范围

### 包含

- 不同会话并行运行。
- 同一会话内继续互斥，运行中禁止重复发送或排队到同一上下文。
- 修复 thinking 模型并发和工具调用时的 `reasoning_content` 回传问题，避免 400。
- 新 run 保存完整可审计事件流：`reasoning_content`、answer delta、tool call、tool result、状态更新、错误、最终答案。
- 默认前端只展示简约进度；展开日志或复制诊断时能追溯 provider 和工具链路细节，且 `reasoning_content` 完整可见。
- 同一会话后续允许切换 thinking/non-thinking 模型，但上下文回放按当前模型兼容处理。

### 不包含

- 全局并发上限。
- 全局任务队列。
- 旧失败 run 补数据。
- 伪造历史缺失的 `reasoning_content`。
- 将 `reasoning_content` 写入长期记忆、普通聊天消息或默认产物。

## 业务场景

### 场景1：跨会话并行

- 用户在会话 A 提问后，不需要等待 A 完成，就能切到会话 B 发起另一个任务。
- A/B 的状态、日志、工具调用、推理内容、最终答案按各自会话和 run 隔离。
- 任一会话失败不能影响其他正在运行的会话。

### 场景2：同会话互斥

- 用户在同一会话运行中再次发送消息时，系统保持当前“运行中不可发送”的保护。
- 这样避免同一会话历史、工具调用和 reasoning 回传顺序被打乱。

### 场景3：Thinking 工具调用修复

- thinking 模型在 DeepAgents 工具调用过程中产生的 `reasoning_content` 必须保留，并在后续 provider 请求中按要求回传。
- 用户不再看到 `The reasoning_content in the thinking mode must be passed back to the API` 这类 400 失败。

### 场景4：可追溯日志

- 默认日志只显示“AI 正在思考 / 生成 / 调用工具 / 工具返回 / 完成 / 失败”等精简状态。
- 展开日志时可看到对应 run 的详细事件证据，包括完整 `reasoning_content`、工具参数、工具结果、错误和最终答案。
- 这些诊断内容服务于排查和审计，不作为普通聊天回答混入上下文展示。

## 验收口径

- 同时启动两个不同会话，两个会话都能独立运行到完成或独立失败。
- thinking 模型使用工具后，后续调用不再因为缺失 `reasoning_content` 返回 400。
- 每个 run 的日志能按 task/run 追溯完整事件流。
- 默认前端进度保持简洁，展开后能看到完整 reasoning 细节。
- 旧会话不补数据，但新 run 从修复后开始满足完整保存和正确回传。

## 待确认问题

- 无。
