---
name: ai-coding-first
description: 编排当前仓库的 AI Coding 文档初始化或刷新流程，并固定从当前项目根目录的 `.agents/skills/` 读取下游技能。适用于用户要求 AI Coding First、项目 coding 初始化、刷新 codebase map/coding maps/AGENTS map/harness docs、创建或优化 AGENTS.md，或希望按顺序依次调用 `$gsd-map-codebase`、`$coding-maps`、`$agents-map`、`$compound-harness-docs`、`$create-rules`，为 backend/frontend 等子项目生成或更新中文文档；如果对应文档不是中文，必须修改成中文。
---

# AI Coding First

本 skill 用于按固定顺序调用当前项目内置 skills，为当前仓库执行一套 AI Coding 文档初始化或刷新流程：

1. `$gsd-map-codebase`
2. `$coding-maps`
3. `$agents-map`
4. `$compound-harness-docs`
5. `$create-rules`

这是一个编排型 skill。不要重新实现下游 skill 的逻辑；必须读取每个下游 skill 自己的 `SKILL.md` 并遵守它的流程。

## 文档语言要求

- 默认用简体中文生成或修改本流程涉及的所有长期文档，除非用户明确要求其他语言。
- 如果现有文档、下游 skill 新生成的文档或本轮修改后的文档不是中文，必须先改成中文，再继续后续步骤或结束任务。
- 适用范围包括子项目 `.planning/codebase/` fact docs、`coding_maps/SYSTEM_MAP.md`、根级 `ARCHITECTURE.md`、`INTERFACES.md`、`AGENTS.md`、harness/codebase 沉淀文档以及下游 skill 约定的等价文档。
- 翻译或改写时保留代码标识符、文件路径、命令、配置键、API 名称和事实结构；只把说明性文字改成中文。

## 项目内技能位置

- 默认把当前工作目录视为项目/仓库根目录，除非用户明确给出其他项目路径。
- 下游 skill 必须从该项目根目录下的 `.agents/skills/<skill-name>/SKILL.md` 读取。
- 不要读取全局用户目录、Codex Home、Auto-Coding 仓库或其他项目里的同名 skill。
- 当前项目不一定是 Auto-Coding；只要该项目根目录包含 `.agents/skills/`，就以该目录为准。
- 如果项目内缺少某个下游 skill，先报告缺失的项目内路径，再询问用户是否允许使用其他来源；不要自动回退到全局路径。

## 工作流

### 1. 确认仓库范围

- 默认把当前工作目录视为仓库根目录，除非用户明确给出其他路径。
- 在状态更新和最终回复中保留用户明确指定的 cwd 和路径风格。
- 修改前先运行 `git status --short`，确认当前工作区是否已有变更。
- 不要回滚、覆盖或清理与本次任务无关的用户改动。

### 2. 发现需要映射的子项目

查找需要生成 codebase map 的子项目：

- 优先选择同时包含源码、配置或测试标记的目录，例如 `pyproject.toml`、`package.json`、`go.mod`、`Cargo.toml`、`pom.xml`、`src/`、`app/`、`tests/` 或已有 `.planning/codebase/`。
- 常见目录名包括 `backend`、`frontend`、`api`、`web`、`apps/*`、`packages/*`。
- 跳过生成目录、依赖目录、缓存目录、本地工具目录和 E2E 证据目录，例如 `.git`、`.agents`、`.venv`、`node_modules`、`.next`、`.next-dev`、`dist`、`build`、`coverage`、`test-results`、带时间戳的 E2E evidence 目录。
- 如果用户明确指定子项目，只处理用户指定的子项目。
- 如果子项目发现结果有歧义，先问一个简短澄清问题，确认后再写文档。

### 3. 为每个子项目运行 `$gsd-map-codebase`

对每个发现到的子项目调用当前项目内的 `$gsd-map-codebase` skill，并把输出限定到该子项目自己的 `.planning/codebase/` 目录。

必须做到：

- 读取 `<当前项目根>/.agents/skills/gsd-map-codebase/SKILL.md`。
- 遵守 `$gsd-map-codebase` 对已有 map 的处理规则；是否 refresh、update 或 skip，以该 skill 流程和用户指令为准。
- 生成或刷新标准 codebase fact 文件，通常包括：
  - `ARCHITECTURE.md`
  - `STRUCTURE.md`
  - `STACK.md`
  - `INTEGRATIONS.md`
  - `CONVENTIONS.md`
  - `TESTING.md`
  - `CONCERNS.md`
- 上述 fact docs 的说明性内容必须是中文；如果下游输出不是中文，立即改成中文。
- 把生成结果保留在子项目内部，例如 `backend/.planning/codebase/`、`frontend/.planning/codebase/`。
- 除非仓库本身就是单项目，或用户明确要求根级映射，否则不要创建根级 `.planning/codebase/`。
- 不要读取或引用真实本地密钥文件，例如 `.env`、`.env.local` 或私有凭据文件；需要配置事实时使用示例文件、配置代码和 README。

### 4. 运行 `$coding-maps`

所有子项目 fact map 可用后，调用 `$coding-maps`。

必须做到：

- 读取 `<当前项目根>/.agents/skills/coding-maps/SKILL.md`。
- 生成或刷新 `coding_maps/SYSTEM_MAP.md`。
- `SYSTEM_MAP.md` 必须用中文表达；如果已有内容或生成结果不是中文，改成中文后再继续。
- 按该 skill 要求，综合根级文档、子项目 `.planning/codebase/` facts 和稳定的 `asset/*.md` 知识包。
- 保持 `SYSTEM_MAP.md` 在系统地图层，不要复制大量底层实现细节。

### 5. 运行 `$agents-map`

系统地图存在后，调用 `$agents-map`。

必须做到：

- 读取 `<当前项目根>/.agents/skills/agents-map/SKILL.md`。
- 使用当前子项目的 `.planning/codebase/` 目录作为事实来源。
- 按该 skill 的文档分层生成或刷新根级导航和系统文档：
  - `ARCHITECTURE.md`
  - `INTERFACES.md` 或等价系统级接口文档
  - `AGENTS.md`
- 上述根级文档必须用中文表达；如果已有内容或生成结果不是中文，改成中文后再继续。
- 保持 `AGENTS.md` 简洁、导航型。系统说明放入 `ARCHITECTURE.md`，接口细节放入 `INTERFACES.md`，实现事实留在子项目 `.planning/codebase/`。

### 6. 运行 `$compound-harness-docs`

调用 `$compound-harness-docs`，把当前分支中稳定、仍然成立的开发知识沉淀回 harness/codebase 文档。

必须做到：

- 读取 `<当前项目根>/.agents/skills/compound-harness-docs/SKILL.md`。
- 遵守该 skill 的事实优先级：当前代码、相对默认分支的 git diff/log、`tasks/*/progress.txt` 中的 Codebase Patterns、再到 `tasks/*/prd.json`。
- 只修改文档文件。
- 写入或更新的 harness/codebase 文档必须用中文表达；如果沉淀内容来自英文日志或英文旧文档，改写成中文后再落文档。
- 不要把自动化工具、validator、progress log、agent harness 等实现细节写入项目文档。
- 如果 progress log 中的经验已经不被当前代码支持，不要写入长期文档。

### 7. 最后运行 `$create-rules`

所有 codebase map、系统地图、agents map 和 harness 文档完成后，最后调用当前项目内的 `$create-rules` skill，为当前仓库创建或优化根级 `AGENTS.md`。

必须做到：

- 读取 `<当前项目根>/.agents/skills/create-rules/SKILL.md`。
- 按该 skill 的创建/优化模式处理当前仓库根目录的 `AGENTS.md`。
- 如果 `AGENTS.md` 已存在，保留已有项目特有规则、人工约束、关键命令和注意事项，并按模板结构整理、补充、去重。
- 如果 `AGENTS.md` 不存在，按 `$create-rules` 的内置模板初始化，并用当前代码库证据替换占位内容。
- 只写对 AI 编码代理有帮助的规则、命令、结构和约定；不要把 `AGENTS.md` 写成完整项目文档。
- 最终 `AGENTS.md` 必须用中文表达；保留命令、路径、配置键和代码标识符的原文。

## 校验

文档型运行必须至少执行：

```bash
git diff --check
```

还要扫描新生成或改动的文档，避免误写常见密钥/token 模式。

校验时还必须快速复核本轮生成或修改的文档语言：如果说明性正文仍有大段非中文内容，先改成中文再汇报完成。

如果本轮只改文档，不要运行代码测试或浏览器 E2E，除非某个下游 skill 明确要求，或用户明确要求。最终回复中说明跳过代码测试/E2E 的原因是“仅文档变更”。

如果过程中意外修改了代码、行为、脚本、配置或测试，立即停下来重新按仓库 `AGENTS.md` 的规则评估验证范围。

## 最终回复

最终回复需要简短说明：

- 映射了哪些子项目。
- 生成或刷新了哪些根级/系统级文档，包括 `AGENTS.md`。
- 运行了哪些校验。
- 是否有下游 skill 找不到或执行失败。
- 变更是否已提交；如果未提交，说明当前状态。
