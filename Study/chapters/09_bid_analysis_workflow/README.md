# 09 招投标分析工作流

## 学习目标

你要理解招投标分析是建立在通用 Agent 平台上的一个业务主题：

- 平台负责 Task、Run、Event、Resource、Artifact。
- 业务层定义招标/投标文档如何分类、如何对比、如何产生证据和报告。
- 当前仓库已经沉淀了招投标分析知识包，但完整 PDF ingest/compare 生产流水线仍需要结合源码进一步确认，不能把知识包里的未来模块当作已实现代码。

## 前置知识

- 招标文件：定义规则、评分项、资格条件。
- 投标文件：投标人对规则的响应、报价、资质、方案。
- 证据锚点：把结论绑定到来源文件、页码、摘录或结构化路径。

## 必读文档和代码

- `asset/bid_analysis_workflow_knowledge_pack.md`
- `asset/tender_workflow_breakdown.md`
- `asset/deepagents_platform_knowledge_pack.md`
- `backend/app/execution/resources.py`
- `backend/app/runner/core.py`
- `backend/skills/*/SKILL.md`

## 本章主线

把业务拆成三层：

1. 当前已实现的平台能力：上传资源、工具读取、run-scoped artifact、事件日志。
2. 当前已沉淀的业务知识：招标骨架、投标评审、compare、证据锚点。
3. 需要未来实现或结合源码进一步确认的模块：PDF ingest、compare result renderer、evidence preview API、manual override。

## 核心业务逻辑

### 文档不是只有“文件”

招投标分析通常要先判断：

- 哪些是招标文件？
- 哪些是投标文件？
- 是否至少有两个投标人文档可对比？
- 证据来自哪个文件、哪一段、哪张表？

### 围串标分析看什么？

常见线索包括：

- 多份投标文件出现高度相似措辞。
- 报价规律异常接近。
- 联系人、地址、格式、错误拼写重复。
- 响应条款、技术方案、排版结构异常一致。

这些只是风险线索，不等于最终法律结论。系统应该输出证据、风险解释和不确定性。

### 报告是 Artifact

最终 HTML/Markdown/JSON 报告应作为 run-scoped artifact 注册，让前端通过 artifact API 打开或下载。

## 结合项目分析

如果把业务知识和平台代码映射起来，最适合初学者记住的是这条“平台先行”的路径：

```text
上传招标/投标文件
-> 平台把它们保存成 task-scoped uploads
-> Agent 通过 resource tools 按需读取
-> 知识包提供“如何分类、如何比较、如何做证据锚点”的业务规则
-> 分析结果写成 artifact
-> 前端只负责展示报告和过程日志
```

所以这一章的学习重点不是“把知识包当代码背”，而是理解：

- 平台已经给了什么能力
- 业务层还需要补什么模块
- 哪些判断现在只能写“需要结合源码进一步确认”

## 当前源码能确认什么

目前能从源码可靠确认：

- 通用上传格式支持 `.md`、`.json`、`.txt`、`.docx`、`.xlsx`、`.xlsm`。
- 上传资源通过 `list_uploaded_resources`、`inspect_resource`、`read_resource_text`、`read_resource_table` 按需读取。
- 产物下载走 task/run artifact API。
- Runner 可以给 Agent 注入 resource manifest 和 SKILL.md。

需要结合源码进一步确认或未来实现：

- PDF ingest 阶段。
- 招标 review、投标 review、compare renderer 的生产模块。
- evidence preview API。
- 人工复核 override API。

## 你可能卡住的问题

### 招投标业务逻辑应该写死在前端吗？

不应该。前端展示任务和产物，业务分析应在后端 Agent、工具、技能和知识包中沉淀。

### 为什么证据要结构化？

结构化证据能追溯来源、生成报告、做测试断言，也能避免只输出一段“看起来很像”的主观描述。

## 为什么本章放在最后

因为只有先学完 `Task / Run / Event / Resource / Artifact / SSE` 这些平台概念，你才看得懂：

- 为什么业务规则优先沉淀在知识包
- 为什么 PDF compare 不是“写个 prompt”就算落地
- 为什么证据锚点、artifact、人工复核这些边界要分开设计

## 动手练习

运行：

```bash
python Study/chapters/09_bid_analysis_workflow/mini_unit.py
```

尝试把 `requires_at_least_two_bidders` 改成允许 1 份投标文件，再运行。你会看到失败。这个失败说明“对比分析”至少需要两个投标主体。

练习还会读取 `asset/` 知识包和当前源码，确认哪些是已实现平台能力，哪些是业务设计边界。

## 自测题

1. 招标文件和投标文件在分析中分别起什么作用？
2. 为什么围串标结果应该表达“风险”而不是直接下法律结论？
3. 业务主题经验应该优先写到哪里？
4. 如果要把 PDF compare 真正落地，为什么不能直接把 PDF 原文塞进 prompt？

## 常见误区

- 误区：知识包里写到的所有模块都已经存在。纠正：知识包也记录未来设计边界，当前源码是否实现要用 `rg` 验证。
- 误区：相似措辞就是串标定论。纠正：它只是风险证据，需要来源、上下文和人工复核。
- 误区：业务逻辑应该写在前端。纠正：前端负责展示和操作，业务分析应在后端 Agent/工具/知识包中沉淀。
