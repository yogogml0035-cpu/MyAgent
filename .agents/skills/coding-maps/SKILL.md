---
name: coding-maps
description: 根据子项目 `.planning/codebase/` 事实文档、根级架构/接口文档和长期知识包，生成或刷新仓库级 `coding_maps/SYSTEM_MAP.md`。当用户要求创建 coding map、系统地图、跨项目架构手册、后端/前端集成说明、AI 可读的大型系统说明书，或需要说明子项目交互关系、依赖关系、调用链、接口边界，以及后端、前端、跨系统修改前应阅读哪些 codebase 文档时使用。
---

# Coding Maps

## 概览

创建根级 `coding_maps/SYSTEM_MAP.md`，帮助后续 AI 理解多个子项目如何组成一个整体系统。该地图应综合已有事实，不替代各子项目 `.planning/codebase/` 文档，也不替代根级导航文档。

## 工作流

1. 除非用户指定其他路径，否则把当前工作目录视为仓库根目录。
2. 运行 `scripts/collect_map_sources.py <repo-root>`，发现可能需要读取的源文档。Windows / Codex 环境优先通过同目录的 PowerShell wrapper 运行，避免依赖 PATH 中存在裸 `python` 命令。
3. 只读取脚本报告中与任务相关的文件，优先读取根文档和子项目 `.planning/codebase/` 事实文档。
4. 如果仓库根目录下不存在 `coding_maps/`，先创建该目录。
5. 生成或刷新 `coding_maps/SYSTEM_MAP.md`。
6. 刷新已有 `coding_maps/SYSTEM_MAP.md` 时，保留仍然正确的内容；只有源文档明确反驳旧内容时，才删除或改写过时结论。
7. 如果只改文档，至少运行 `git diff --check`。如果同时改了代码或行为，不要只依赖本 skill，应按仓库规则运行对应测试。

## 源文档优先级

源文档存在时，按下面顺序阅读：

1. 根级 `AGENTS.md`、`ARCHITECTURE.md`、`INTERFACES.md`。
2. 各子项目的 `.planning/codebase/ARCHITECTURE.md`、`INTEGRATIONS.md`、`STRUCTURE.md`、`TESTING.md`、`CONVENTIONS.md`、`CONCERNS.md`。
3. `asset/*.md` 下稳定的领域或平台知识包。
4. 只有高优先级来源缺失或含糊时，才读取根级 `README.md` 或子项目 `README.md` 辅助判断。
5. 刷新时读取已有 `coding_maps/SYSTEM_MAP.md`。

不要把 `.agents/` 这类被忽略的本地 agent 工具目录或生成型运行时目录当作产品事实来源；除非用户明确询问 agent tooling。

## SYSTEM_MAP.md 内容

写成一份简洁但足够有用的跨子项目理解手册。优先包含这些部分：

- 系统目的和仓库形态。
- 子项目职责表。
- 跨子项目调用链和数据流。
- 后端到前端的接口边界。
- 有源文档支撑时，说明共享状态、存储、事件、上传、产物、认证和 provider 边界。
- 子项目之间的依赖和归属规则。
- 按任务分类的阅读指南：
  - 后端业务、API、存储、runner 修改
  - 前端工作区、状态、上传、产物、SSE 修改
  - 跨系统接口修改
  - 视觉或 UX 修改
  - 领域流程或报告生成修改
- 集成风险检查清单和验证入口。
- 使用过的源文档索引。

把地图保持在系统层。链接到子项目事实文档，而不是复制大量底层实现细节。证据不足时，用“当前源文档未确认”或“需要确认”表达，不要编造依赖关系。

## 写作规则

- 使用 Markdown。
- 生成文档中的路径统一使用相对仓库根目录的路径。
- 区分已确认事实和基于事实得到的操作建议。
- 保持安全边界：不要写入密钥、私密客户数据、provider key、数据库 URL 或私密样例。
- 除非用户明确要求，不要修改根级 `AGENTS.md`、`ARCHITECTURE.md` 或 `INTERFACES.md`；本 skill 默认只输出 `coding_maps/SYSTEM_MAP.md`。
- 如果仓库已有明确的文档维护规则，遵守这些规则，并在最终回复中说明跳过了哪些验证。

## 辅助脚本

使用 `scripts/collect_map_sources.py` 发现可能输入。

Windows PowerShell / Codex 环境优先使用：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File <skill-dir>\scripts\collect_map_sources.ps1 <repo-root>
```

Linux / WSL 环境可直接使用：

```bash
python3 <skill-dir>/scripts/collect_map_sources.py <repo-root>
```

如果 Windows 下 `python` 不在 PATH 中，不要据此判断后端虚拟环境损坏。若 `backend\.venv\Scripts\python.exe` 在普通沙箱中报 `Unable to create process`、`Access denied` 或类似启动器错误，先用真实 Windows PowerShell / `powershell.exe -NoProfile` 复查；venv 启动器可能只是被沙箱拦截了对外部基础解释器的调用。

脚本会输出 JSON，列出发现的根文档、子项目 codebase 文档、asset 知识包、已有地图文件和目标输出路径。把它当成输入发现工具，不要用它替代对源文档的阅读和综合。
