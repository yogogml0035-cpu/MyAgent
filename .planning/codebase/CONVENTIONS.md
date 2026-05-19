# 编码约定

**分析日期：** 2026-05-19

## 命名

- 后端 Python 文件使用 `snake_case.py`。
- 后端测试文件使用 `test_*.py`。
- 前端非组件模块使用 `kebab-case.ts`。
- 前端 React 组件文件使用 `PascalCase.tsx`。
- 前端 Node 测试使用 `test_*.test.ts`。
- Playwright spec 使用 `test_*.spec.mjs`。
- 后端 API 字段使用 `snake_case`。
- 前端归一化后的状态字段使用 `camelCase`。

## 后端风格

- 后端模块优先使用 `from __future__ import annotations`。
- 使用 `app.*` 绝对导入。
- 路由层保持薄，生命周期规则交给 storage、runner、model registry 和 helper。
- 公共边界使用 Pydantic schema、dataclass 或明确类型。
- API 预期错误转为 `HTTPException` 和稳定 detail。
- runner 错误要落到任务终态和事件，不只写日志。
- 后端格式遵循 Ruff line length 100 和 Python 3.11 target。

## 前端风格

- React 组件尽量只展示，不直接调用后端。
- 后端 I/O 放在 `frontend/lib/task-api.ts`。
- 副作用和工作流状态放在 `frontend/hooks/use-task-workspace.ts`。
- 纯状态转换放在 `frontend/app/task-state.ts`。
- 纯展示投影放在 `frontend/app/workspace-view.ts`。
- 不引入 TypeScript path alias，除非同步 tsconfig、lint 和测试。
- 视觉变化优先复用 `frontend/app/globals.css` 里的现有 token，并先读 `DESIGN.md`。

## 错误处理

- 后端把上传、模型、任务状态、路径和权限错误映射为明确 HTTP 状态。
- 后端 best-effort 行为失败时记录日志并尽量不中断主流程。
- 资源工具返回结构化错误，不直接让 agent 运行崩掉。
- 前端对网络错误、非 OK 响应和非 JSON 响应做防御性处理。
- 前端不要信任后端任意 artifact URL，必须经过信任检查。

## 日志和注释

- 后端使用 Python `logging`。
- 前端应用代码避免提交 `console.log`。
- 用户可见运行诊断优先走事件日志，而不是进程日志。
- 注释只解释安全、生命周期、streaming 或协议边界，不重复代码表面含义。

## 文档和知识

- 根 `AGENTS.md` 保持导航型。
- 系统边界变化同步 `ARCHITECTURE.md` 和 `INTERFACES.md`。
- 子项目事实变化刷新对应 `.planning/codebase/`。
- 稳定业务规则和回归风险写入 `asset/` 知识包。
