# 后端编码约定

**分析日期：** 2026-05-25

## 命名模式

- 应用模块使用小写 `snake_case`：`task_titles.py`, `memory_admin.py`, `reasoning_trace.py`。
- HTTP route 按 API surface 分组：`api/tasks.py`, `api/files.py`, `api/artifacts.py`, `api/streaming.py`。
- 领域包按职责分组：`agent/`, `models/`, `streaming/`, `security/`, `skills/`, `execution/`, `tools/`。
- 包目录保留 `__init__.py`。
- pytest 文件使用 `test_<subject>.py`，尽量镜像 app package。
- 项目技能放在 `backend/skills/<skill-name>/SKILL.md`。
- 公共函数、私有 helper、fixture 都用 `snake_case`；模块私有 helper 用 `_` 前缀。
- 有副作用或校验语义的函数优先动词开头：`validate_run_id`, `normalize_artifact_name`, `authorize_task_request`。
- async 函数用于 I/O 或 event-loop 边界：API handler、runner start/cancel、streaming。
- module constants 使用 `UPPER_SNAKE_CASE`。
- DTO 和服务类使用 `PascalCase`。

## 类型约定

- API request/response 使用 Pydantic `BaseModel`，集中在 `backend/app/schemas.py`。
- 不可变内部 record 和配置使用 frozen dataclass，如 `Settings`, `RetrievedMemory`, resource records。
- 注入依赖使用 `Protocol`，如 `RunnerStorage`, `RunnerMemoryService`, `ConversationStorage`, `LongTermMemoryStorage`。
- 使用 Python 3.11 语法：`str | None`, `list[EventRecord]`, `dict[str, Any]`。
- 稳定字符串域使用 `Literal` 或 `TypeAlias`。

## 代码风格

- Ruff 是格式和 lint 权威，配置在 `backend/pyproject.toml`。
- 目标 Python 版本是 3.11，尽量控制 100 字符行宽。
- 模块顶部使用 `from __future__ import annotations`。
- 文本文件 I/O 显式指定 UTF-8。
- `# noqa` 只用于窄范围、有意的例外。
- 导入顺序：future、标准库、第三方、本地 `app.*`、测试专用 `tests.*`。
- pytest 配置了 `pythonpath = ["."]`，测试中导入 `app.*`。
- 应用模块内既有相对导入也有 `app.*` 绝对导入，编辑时跟随周围风格。

## 错误处理

- API route 把 storage/validation error 转成明确 HTTP response。
- 404 表示 task/artifact 不存在，400 表示输入无效，409 表示运行状态冲突，413 表示上传或请求过大。
- 对不应泄露内部细节的包装使用 `from None`；保留底层 cause 时使用 `from exc`。
- 领域异常集中定义并跨边界处理：`RequestBodyTooLarge`, `ModelProviderError`, `MemoryServiceError`, `UploadConflictError`, `UploadLimitError`, `SecretScanViolation`。
- 工具函数对预期失败返回结构化或可读错误，不让 agent run 崩溃。
- 可恢复后台失败应 log 后继续，例如标题生成、memory recall、resource manifest、memory extraction。
- 生产必需服务缺失应在 startup fail fast。

## 日志

- 使用 Python 标准 `logging`。
- 需要日志的模块定义 `logger = logging.getLogger(__name__)`。
- 正常生命周期用 `logger.info()`。
- 可恢复异常用 `logger.warning(..., exc_info=True)`。
- 重新抛出的未知 runner failure 用 `logger.exception()`。
- 不记录 secret 值；secret 扫描和脱敏在 `backend/app/security/scanner.py`。

## 注释

- 模块 docstring 用于说明清晰的所有权或集成边界。
- 公共 helper 和服务如果定义合同，应写简短 docstring。
- 行内注释只解释非显然行为或兼容性要求，例如 final-answer synthetic event、LangGraph store 兼容。
- 不要写复述赋值或断言的空注释。

## 函数与模块设计

- route function 保持小而薄，把状态变更委托给 storage、runner、model、memory 或 execution module。
- 大型 orchestrator 可存在于 `storage.py`、`runner/core.py`、`execution/resources.py`，但应守住单一领域边界。
- 可选行为用 keyword-only 参数表达。
- 边界返回 typed DTO 或 domain record。
- 避免 broad re-export；多数 `__init__.py` 只作为 package marker。

## 技能相关约束

- 项目技能是运行时一等内容，放在 `backend/skills/<skill>/SKILL.md`。
- 技能文件通过 `backend/app/skills/project.py` 和 `backend/app/skills/loader.py` 发现。
- 运行时技能源被 `backend/app/agent/factory.py` 只读挂载；更改 skill access 时保留 `_ReadOnlyBackend` 模式。
- `web_research` 依赖 SearXNG 工具；runner 会为该技能追加快速联网核查提示、5 次总搜索预算、禁止子任务委派，并在没有明确交付文件要求时关闭 `create_word_document`。`code_review` 依赖安全、测试和代码质量约定。

---

*约定分析：2026-05-25*
