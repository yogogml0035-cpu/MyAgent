# 后端编码约定

**分析日期：** 2026-05-19

## 命名

- 模块文件使用 `snake_case.py`。
- 函数和变量使用 `snake_case`。
- 常量使用 `UPPER_SNAKE_CASE`。
- Pydantic model、dataclass、protocol 和类型别名使用 `PascalCase`。
- pytest 文件使用 `test_*.py`。
- API 字段保持后端 `snake_case`。

## 代码风格

- 模块顶部优先使用 `from __future__ import annotations`。
- 使用 `app.*` 绝对导入。
- Ruff line length 为 100，target 为 Python 3.11。
- 路由处理函数保持薄，复杂逻辑下沉到 storage、runner、model registry 或 helper。
- 边界敏感函数优先使用显式类型和 keyword-only 参数。
- 公共返回值优先使用 Pydantic model、dataclass 或结构明确的数据。

## 错误处理

- API 层把预期错误转换为 `HTTPException`。
- 用户可见 detail 应保持稳定。
- 任务运行失败必须写入任务终态和事件。
- best-effort 行为失败时记录日志并继续，例如标题生成、记忆召回、记忆写入。
- 上传和 artifact 路径错误使用明确的 400/404/409/413 等状态。
- 资源工具返回结构化 JSON 错误，不把普通输入错误抛进 agent loop。

## 日志

- 使用 `logging.getLogger(__name__)`。
- 可降级失败使用 `logger.warning(..., exc_info=True)`。
- 意外 runner 失败使用 `logger.exception()`。
- 用户可见诊断优先通过 `EventRecord` 持久化。

## 模块边界

- API 路由在 `backend/app/api/`。
- 存储契约在 `backend/app/storage.py`。
- runner 生命周期在 `backend/app/runner/core.py`。
- stream 适配在 `backend/app/streaming/`。
- 工具注册在 `backend/app/tools/registry.py`。
- 模型 provider 在 `backend/app/models/`。

## 注释

- 对安全、生命周期、streaming、路径约束和协议边界加短注释。
- 避免解释显而易见的赋值或循环。
- 测试优先用清晰的测试名表达行为。
