# 后端风险和关注点

**分析日期：** 2026-05-19

## 技术债

- `backend/app/storage.py` 同时承担 schema、任务状态、事件、上传、产物、cache、memory 和 store，职责过重。
- `backend/tests/fakes.py` 手工复制 storage 行为，容易和生产 Postgres 行为漂移。
- `backend/app/memory.py` 同时负责 embedding、Qdrant、抽取、脱敏和写入，边界偏大。
- `build_agent_with_middleware()` 容易和 `create_deep_agent()` 默认 middleware 行为重复，需要谨慎使用。
- subagent 并发配置是否真正传入 agent 创建路径需要回归确认。

## 已知问题

- 自动标题生成在 runner 调度前等待，慢模型可能延迟后台运行接管。
- `_inspect_excel()` 异常路径可能绕过 workbook close。

## 安全关注

- 非 loopback 访问依赖单个本地 token，不是完整用户会话系统。
- SSE query token 可能出现在日志或诊断中。
- 本地 env 中的 provider key、数据库 URL、Qdrant URL 和 embedding key 不能进入文档或测试。
- 长期记忆脱敏不是完整 DLP，不能保存上传原文或客户敏感内容。
- Office 文件解析在 API 进程中执行，需依赖大小限制、扩展名限制和库安全。

## 性能关注

- storage 每次操作新建 Postgres 连接，SSE 轮询会放大开销。
- 任务列表和任务详情缺少分页。
- 上传处理包含同步 IO、hash 和 JSON 校验。
- 资源工具重复解析上传文档，没有解析缓存。

## 脆弱区域

- `storage.start_run()`、`runner.start_background()`、run_id、事件、终态和 final answer 必须保持顺序一致。
- LangGraph/DeepAgents stream chunk 形状变化会影响 `v2_adapter` 和 `event_converter`。
- SSE cursor recovery 依赖后端完整有序事件。
- artifact 路径规范必须和前端 URL 信任检查保持一致。

## 扩展限制

- 当前没有 durable job queue、lease、heartbeat 或 crash recovery。
- 当前不支持多 worker 或多主机 active run ownership。
- 当前上传和产物是本地文件系统，不适合无共享存储的横向扩展。
- 当前没有多用户权限模型。

## 建议优先级

1. 让 runner 调度不被自动标题阻塞。
2. 修复 Excel workbook close 异常路径。
3. 给 storage 拆分公共契约并加强 fake/Postgres parity 测试。
4. 为事件和任务历史引入分页或压缩。
5. 增强长期记忆和上传解析的安全测试。
