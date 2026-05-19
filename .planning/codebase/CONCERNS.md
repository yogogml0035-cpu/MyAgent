# 风险和关注点

**分析日期：** 2026-05-19

## 技术债

- `backend/app/storage.py` 承担任务、运行、事件、上传、产物、缓存、长期记忆和 store 多个契约，改动影响面大。
- `backend/tests/fakes.py` 手工模拟生产 storage，存在 fake 和 Postgres 行为漂移风险。
- `frontend/app/task-state.ts` 和 `frontend/app/workspace-view.ts` 承担大量归一化、投影和安全判断，文件偏大。
- `backend/app/memory.py` 同时处理 embedding、Qdrant、抽取 prompt、脱敏、存储和索引，集成边界偏重。
- `MYAGENT_MAX_CONCURRENT_SUBAGENTS` 配置已存在，但需确认是否真正传入 DeepAgents 创建路径。

## 已知问题

- 自动标题生成在 runner 调度前执行，慢 provider 可能让任务处于 `running` 但后台 runner 尚未接管。
- Excel inspection 异常路径可能没有关闭 workbook，需要 `try/finally` 回归测试。
- `frontend/e2e-playwright/test_storage_memory_e2e.mjs` 不是标准 `*.spec.mjs`，容易被误认为默认 Playwright spec。

## 安全关注

- `NEXT_PUBLIC_MYAGENT_TOKEN` 是浏览器可见 token；SSE query token 可能出现在日志或诊断中。
- 后端 `.env` 和前端 `.env.local` 是本地私密文件，不能复制到文档、测试或知识包。
- 长期记忆脱敏主要依赖规则和白名单，不是完整 DLP。
- HTML artifact 即使 sandbox 预览，也仍是不可信内容。
- Office 文档解析在后端进程内完成，依赖上传大小限制和解析库安全。

## 性能瓶颈

- storage 操作每次新建 Postgres 连接，SSE 轮询会放大连接开销。
- 任务列表和任务详情缺少分页，长历史会拖慢后端读取和前端归一化。
- 上传保存时同步文件 IO 和 hash 可能在 storage lock 下执行。
- 资源工具重复解析 Word/Excel 文件。
- 前端 live log projection 对大事件流不是增量计算。

## 脆弱区域

- runner、storage、terminal event、final answer、SSE 可见性和 memory write 的顺序必须保持一致。
- LangGraph/DeepAgents stream chunk 形状变化会影响事件转换和前端日志展示。
- SSE cursor recovery 依赖后端完整有序事件和前端按事件 ID 去重。
- artifact URL、run scope、token attachment 和 HTML preview 必须跨前后端保持一致。
- browser E2E 并不是所有 CI 默认入口，行为变更需要主动选择对应场景。

## 扩展限制

- 当前不支持多 worker、多主机 runner ownership 或 crash recovery。
- 当前文件存储是本地目录，不适合无共享卷的横向扩展。
- 当前没有多用户账号、RBAC、OAuth 或 cookie session。
- 当前没有统一 retention、quota、批量清理或事件压缩策略。

## 优先改进方向

- 给 storage 拆出更清晰的公共契约，并建立 fake/Postgres 共享契约测试。
- 让 runner 调度早于 best-effort 标题生成。
- 为事件、消息和任务历史增加分页或压缩策略。
- 将浏览器关键路径纳入更稳定的 E2E 入口。
- 为长期记忆、上传解析和 artifact 预览补更明确的安全边界测试。
