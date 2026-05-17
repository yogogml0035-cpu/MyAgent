# 08 安全、记忆与测试

## 学习目标

你要理解三个长期边界：

1. 安全：默认本机访问，非本机访问必须 token；密钥不能进前端。
2. 记忆：只保存高层、脱敏、稳定的用户事实或项目规则。
3. 测试：行为变化要同步单元/集成/浏览器 E2E。

## 前置知识

- loopback：本机地址，例如 `127.0.0.1`、`localhost`。
- token：调用 API 时证明访问者被允许的令牌。
- 向量记忆：把文本摘要转成向量后用于语义检索。

## 必读代码

- `backend/app/main.py`
- `backend/app/security/scanner.py`
- `backend/app/memory.py`
- `backend/app/config.py`
- `backend/tests/`
- `frontend/tests/`
- `frontend/e2e-playwright/README.md`

## 本章主线

安全边界先看 `main.py` 的中间件，再看 `memory.py` 的长期记忆白名单和脱敏，最后看测试目录如何守住这些契约。

## 核心概念

### 本地优先安全边界

没有配置访问 token 时，任务 API 默认只允许 loopback 客户端访问。非本机访问必须配置 token 和 CORS。

前端 `NEXT_PUBLIC_*` 会暴露给浏览器，所以 provider key、数据库 URL、客户文档路径都不能写进去。

SSE 有个特殊点：浏览器 `EventSource` 不能自定义 header，所以 token 会通过 query param 传给 `/stream`，后端鉴权也支持从 query param 读取。

### 长期记忆只存稳定摘要

允许保存：

- `preference`
- `profile_fact`
- `project_rule`
- `stable_workflow`

禁止保存：

- 上传原文
- 完整产物
- 密钥、token、授权头
- 原始工具日志
- 客户敏感文本

### 测试分层

- 后端单元测试：`backend/tests/unit/`
- 后端集成测试：`backend/tests/integration/`
- 前端单元测试：`frontend/tests/`
- 浏览器 E2E：`frontend/e2e-playwright/`

行为变更不能只靠“看代码没问题”。必须有对应测试，前端关键流程还要实际浏览器 E2E 和截图证据。

## 你可能卡住的问题

### 为什么长期记忆不能存完整报告？

长期记忆会被向量化、跨任务召回。如果存完整报告或客户原文，会扩大敏感信息传播范围。

### 为什么 warning 也可能让 CI 失败？

前端 lint 使用 `eslint . --max-warnings=0`，warning 会导致非零退出码。

## 动手练习

运行：

```bash
python3 Study/chapters/08_security_memory_testing/mini_unit.py
```

尝试把 `ALLOWED_MEMORY_TYPES` 加上 `"temporary_fact"`，再运行。你会看到失败。这个失败说明临时事实不应该进入长期记忆。

练习还会读取 `main.py`、`memory.py`、`scanner.py`，确认 token、loopback、记忆白名单和敏感扫描在源码中存在。

## 自测题

1. 为什么 provider API key 只能在后端环境里？
2. 哪些改动需要浏览器 E2E？
3. 为什么测试文件名必须以 `test_` 开头？
4. 长期记忆和同一 task 的会话上下文有什么区别？

## 常见误区

- 误区：本地项目就不需要鉴权。纠正：默认只允许本机；一旦非本机访问就必须 token。
- 误区：长期记忆越多越聪明。纠正：只保存稳定、脱敏、高层摘要，避免污染和泄密。
- 误区：文档学习目录新增练习也要跑浏览器 E2E。纠正：本次是学习资料/独立练习，不改变产品行为；行为变更才需要 E2E。
