---
name: ai-coding-second
description: "按固定顺序编排当前项目 `.agents/skills/` 下的 $prd、$plan-feature、$ralph 技能，把已对齐的需求生成任务目录下的 prd.md、requirements.md、plan.md、prd.json，并输出可复制运行的 WSL 和 Windows Ralph 命令。适用于用户说 AI Coding Second、准备 AI 编码、生成 Ralph 执行准备文件，或希望在需求对齐后按中文 PRD 到计划再到 prd.json 的流程准备执行材料；如果对应文档不是中文，必须修改成中文。"
---

# AI Coding Second

## 目标

把已经和用户对齐过的需求，按固定顺序转成可交给 Ralph 自主执行的一组文件：

```text
tasks/<requirement-slug>/requirements.md
tasks/<requirement-slug>/prd.md
tasks/<requirement-slug>/plan.md
tasks/<requirement-slug>/prd.json
```

最后分别输出可复制运行的 WSL 和 Windows Ralph 命令，让用户自行选择运行环境。

## 输入要求

- 使用用户本轮已经对齐的需求内容作为源输入。
- 如果本轮缺少足够的需求目标、范围或验收口径，先向用户补问关键澄清问题，再继续。
- 全部 Markdown 产物使用简体中文生成或修改；如果已有或下游生成的 Markdown 不是中文，必须先改成中文，再进入下一步。
- `prd.json` 中面向人的标题、story、验收标准、说明、风险和备注等文本字段也默认使用中文；命令、路径、配置键和代码标识符保持原文。
- 不实施功能代码，不修改业务代码；本技能只准备需求、计划和 Ralph JSON。
- 以当前仓库为代码分析上下文，默认在仓库根目录执行。
- 当前项目不一定是 Auto-Coding；下游 skill 位置始终以当前项目根目录的 `.agents/skills/` 为准。

## 项目内技能位置

- 默认把当前工作目录视为项目/仓库根目录，除非用户明确给出其他项目路径。
- 下游 skill 必须从该项目根目录下的 `.agents/skills/<skill-name>/SKILL.md` 读取。
- 不要读取全局用户目录、Codex Home、Auto-Coding 仓库或其他项目里的同名 skill。
- 如果项目内缺少 `$prd`、`$plan-feature` 或 `$ralph`，先报告缺失的项目内路径，再询问用户是否允许使用其他来源；不要自动回退到全局路径。
- 即使运行环境已自动加载同名技能，也要确认实际遵循的是当前项目内对应 `SKILL.md` 的流程。

## 固定编排顺序

严格按下面顺序执行，不跳步，不从仓库中猜测旧任务目录。

### 1. 调用 `$prd`

使用 `$prd` 基于用户已经对齐的需求生成：

- `tasks/<requirement-slug>/prd.md`
- `tasks/<requirement-slug>/requirements.md`

要求：

- 按 `$prd` 的规则生成中文 PRD 和原始对齐需求归档。
- 如果 `prd.md` 或 `requirements.md` 不是中文，立即改成中文后再继续。
- 如果 `$prd` 认为需求仍不明确并提出澄清问题，等待用户回答后再继续后续步骤。
- 记录 `$prd` 实际创建的 `tasks/<requirement-slug>/` 路径，后续步骤必须使用同一个目录。

### 2. 调用 `$plan-feature`

使用 `$plan-feature`，显式传入上一步创建的任务目录：

```text
tasks/<requirement-slug>
```

要求：

- 基于 `prd.md`、`requirements.md` 和当前项目代码生成中文 `plan.md`。
- 如果 `plan.md` 不是中文，立即改成中文后再继续。
- 遵守 `$plan-feature` 的代码库分析、快照和输出规则。
- 如果发现用户本轮补充和任务目录内容冲突，先列出冲突并暂停确认。

### 3. 调用 `$ralph`

使用 `$ralph`，显式传入同一个任务目录：

```text
tasks/<requirement-slug>
```

要求：

- 基于 `prd.md`、`requirements.md`、`plan.md` 和项目相关代码生成 `prd.json`。
- 遵守 `$ralph` 的 story 拆分、验收标准增强、快照、`progress.txt` 初始化和 JSON 修复验证规则。
- `prd.json` 必须写入同一个 `tasks/<requirement-slug>/` 目录。
- 如果 `prd.json` 中面向人的文本字段不是中文，修复为中文后再视为完成。

### 4. 输出 Ralph 命令

确认 `prd.json` 生成并通过 `$ralph` 的修复验证后，同时输出下面两行命令，把路径替换为真实任务目录：

WSL/Linux：

```bash
python3 scripts/ralph/ralph.py  --agent codex --prd-json tasks/<requirement-slug>/prd.json --dashboard-port 7331
```

Windows/PowerShell：

```powershell
python scripts/ralph/ralph-win.py  --agent codex --prd-json tasks/<requirement-slug>/prd.json --dashboard-port 7331
```

## 汇报格式

完成后简要汇报：

- 已创建的任务目录
- 已生成的文件：`requirements.md`、`prd.md`、`plan.md`、`prd.json`
- WSL/Linux Ralph 命令
- Windows/PowerShell Ralph 命令
- 如有未完成步骤，说明卡在哪个阶段以及缺少什么输入或文件
- 明确说明已复核 `requirements.md`、`prd.md`、`plan.md` 和 `prd.json` 的中文要求；如果仍有非中文说明性内容，先修正再汇报完成。

## 下游技能清单

按名称调用技能：`$prd`、`$plan-feature`、`$ralph`。执行前读取当前项目内对应文件：

- `.agents/skills/prd/SKILL.md`
- `.agents/skills/plan-feature/SKILL.md`
- `.agents/skills/ralph/SKILL.md`
