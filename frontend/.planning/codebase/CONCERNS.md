# 前端风险和关注点

**分析日期：** 2026-05-19

## 技术债

- `frontend/app/task-state.ts` 承担大量后端字段、事件、artifact URL 和安全归一化。
- `frontend/app/workspace-view.ts` 承担日志分组、对话排序、诊断 JSON 和展示标签，文件偏重。
- 全局 CSS 与组件 class name 耦合较紧，改 markup 或 class 容易影响多处状态。
- 浏览器 E2E 入口不完全统一，有 standalone 脚本不是标准 Playwright spec。

## 已知问题

- 暂未发现明确的前端-only 功能 bug。
- 系统层面仍需关注 SSE 恢复、artifact URL 安全、history 菜单、上传预览和视觉回归。

## 安全关注

- `NEXT_PUBLIC_MYAGENT_TOKEN` 会暴露在浏览器中。
- SSE token 放在 query 参数中，可能出现在日志或诊断。
- artifact URL 必须保持同源、当前任务范围和可信路径。
- HTML artifact 预览虽然 sandbox，但仍是不可信内容。
- 上传扩展名过滤只是体验，不是安全边界。

## 性能关注

- 大量事件会让状态归一化和 view projection 变慢。
- live log diagnostics 会重复排序、合并和序列化。
- 当前没有任务历史分页或前端虚拟列表。
- E2E 本地证据目录长期积累会占磁盘。

## 脆弱区域

- 后端事件 schema 变化会影响 `task-state.ts` 和 `workspace-view.ts`。
- SSE 重连和事件轮询依赖事件 ID 去重。
- artifact 打开下载涉及 URL 校验、token、object URL 生命周期、弹窗和 sandbox。
- history rename/delete 菜单依赖局部状态、outside click、Escape 和 `window.confirm`。
- upload composer 在文件输入、模型选择、发送/停止按钮和响应式布局之间存在耦合。

## 扩展限制

- 无前端侧分页或虚拟列表。
- 只支持单个后端 origin。
- 无登录、账号、session 或多用户界面。
- 无 retention、quota 或批量清理 UI。
- 浏览器 E2E 不是默认 CI 全量 gate。

## 建议优先级

1. 将状态归一化、artifact 安全和 view projection 按关注点拆小。
2. 把关键浏览器路径纳入更明确的 E2E 命令或 CI 策略。
3. 为长事件流增加分页、虚拟化或 memoization。
4. 增加本地 E2E 证据清理说明或脚本。
5. 任何视觉改动都保持 `DESIGN.md` 和截图证据同步。
