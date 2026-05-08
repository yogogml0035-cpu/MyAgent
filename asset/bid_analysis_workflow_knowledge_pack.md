# 招投标 PDF 分析工作流指导文件

## 背景与范围

本文件用于指导 MyAgent 后续实现类似 Tender Workbench 的招投标 PDF 分析能力。内容来自对用户提供的独立参考网页进行功能与数据结构观察后的归纳，只沉淀架构、契约和实现边界，不复制参考站点中的客户原文、签名 URL、私有路径、运行 ID、密码、原始 prompt 日志或其他敏感信息。

适用场景：

- 新增 PDF 招标文件和投标文件上传能力。
- 新增 PDF 解析、页级 Markdown、canonical JSON、页面图片和版面坐标。
- 新增招标文件评审提取、单份投标文件评审、投标人横向对比。
- 新增 skill 版本选择、图像证据预核验、证据锚点、PDF 聚焦框预览。
- 新增 compare 结果页、人工复核覆盖记录、阶段重跑或追加投标文件。

本文件只作为当前 Agent 项目的改造指导。任务 API、安全边界、run-scoped artifacts、事件脱敏、前端 Hook/API 分层仍以 `asset/deepagents_platform_knowledge_pack.md` 中已有规则为准。

## 业务规则

- 参考网页的核心不是“一次聊天生成答案”，而是一个可追踪的阶段流水线。每个 run 记录输入、阶段状态、事件、产物、模型配置、skill 引用和最终 compare 结果。
- 创建分析时需要收集：一份招标文件、一份或多份投标文件、招标评审模型、投标评审模型、图像核验策略，以及 `tender-review`、`bid-review`、`pdf-image-check` 三类 skill 版本引用。
- MyAgent 当前上传面只支持 `.md` 和 `.json`。引入 PDF 招投标比较时，应新增明确的 PDF ingest 子系统，不能把 PDF 字节静默塞进现有 Markdown/JSON 工作流。
- PDF ingest 阶段应为每份文件生成安全中间产物：原始 layout JSON、canonical document JSON、页级 Markdown、可选页面图片、ingest manifest。公开 API 中只暴露 task/run 相对虚拟路径或 artifact ID。
- 招标文件评审阶段应使用招标 canonical/page Markdown 和后端托管的 skill prompt，生成固定结构的招标评审骨架，覆盖资格、符合性、价格、技术、商务、响应/偏离和特殊规则等章节。
- 投标文件评审阶段应一次只处理一个投标人，并以招标评审骨架为基线。它必须保持招标侧定义的条目顺序和边界，证据不足时保守标记，并输出固定结构 Markdown。
- 图像证据预核验是辅助阶段，不应扩大为整份 PDF 的视觉全文审查。它只选择资格/符合性或图像敏感条目的高价值候选页，按策略渲染页面图片，用视觉 skill 产出短结构化结论，再附加到投标页级 Markdown 中供后续评审吸收。
- Compare 生成应尽量确定性执行。它解析招标评审和各投标评审结果，生成 typed matrices、投标人摘要、风险列表、watchlist、evidence anchors、最终 HTML 和 JSON。
- 证据锚点是独立于 AI 判断的契约。AI 负责提供页码、条目名、短摘录和匹配提示；后端 resolver 用 canonical layout/OCR 的行级 bbox 定位证据，再生成整页高亮图和局部裁剪图。
- 人工复核应作为覆盖层保存，而不是直接抹掉 AI baseline。覆盖记录至少包含 target path、field、before、after、reason_code、reason_text、updated_at。
- 追加投标文件或重跑阶段必须刷新下游产物。重跑招标 ingest 应刷新招标 review、所有投标 review 和 compare；重跑单个投标 ingest 应刷新该投标 review 和 compare；只重跑 compare 不应重算前面解析和评审。

## 输入输出样例

创建 PDF 对比任务：

```text
输入：tender.pdf、bidder-a.pdf、bidder-b.pdf、模型配置、image policy=medium、内置 skill refs。
输出：一个 run，包含阶段事件、run manifest、每份 PDF 的 ingest 产物、招标 review Markdown、每个投标人的 bid review Markdown、compare-result.json、report.html 和可选证据预览图片。
```

skill 引用建议结构：

```json
{
  "skill_refs": {
    "tender_review": {"family": "tender-review", "source": "builtin", "version_id": "default"},
    "bid_review": {"family": "bid-review", "source": "builtin", "version_id": "default"},
    "pdf_image_check": {"family": "pdf-image-check", "source": "builtin", "version_id": "default"}
  }
}
```

证据锚点建议结构：

```json
{
  "schema_version": "evidence_anchor.v1",
  "anchor_id": "bid-01:section-item:qualification:qualification-2",
  "bid_document_id": "bid-01",
  "section_key": "qualification",
  "item_id": "qualification-2",
  "item_title": "医疗器械经营许可证",
  "pages": [11],
  "primary_page": 11,
  "evidence_pages_text": "P11",
  "match_hints": {
    "preferred_match_mode": "line",
    "text_needles": ["医疗器械经营许可证", "经营范围"],
    "excerpt": "脱敏后的短证据摘要"
  }
}
```

证据预览响应建议结构：

```json
{
  "schema_version": "evidence_preview.v1",
  "anchor_id": "bid-01:section-item:qualification:qualification-2",
  "status": "matched",
  "page_no": 11,
  "scale": 2.0,
  "focus_bbox": [89, 46, 507, 405],
  "crop_bbox": [65, 22, 531, 429],
  "image_size": [1191, 1685],
  "page_image_url": "/api/tasks/<task_id>/runs/<run_id>/evidence-anchors/<anchor_id>/preview/page",
  "crop_image_url": "/api/tasks/<task_id>/runs/<run_id>/evidence-anchors/<anchor_id>/preview/crop",
  "matched_text": "有长度上限的脱敏文本"
}
```

未命中文本时的回退：

```text
输入：anchor 声明 P30，但 layout 行文本没有命中 text_needles。
输出：evidence_preview.v1，status=declared_page_fallback，page_no=30，focus_bbox=null，crop_bbox=null，展示声明页整页图。
```

## 边界条件

- PDF 支持不能削弱现有 `.md`/`.json` 原子上传校验。PDF 应有独立的文件数量、单文件大小、总请求大小、页数和文件名限制。
- OCR/VLM/PDF 解析服务属于外部工具。原始响应、签名上传 URL、provider 凭据、绝对路径、全文正文不得进入 task API payload、前端 DOM、复制日志、知识包或测试夹具。
- 公开产物可以包含 task/run 相对虚拟路径、artifact ID、文件名、页码、短摘录和 hash，不得包含本地私有根路径或第三方签名 URL。
- Compare HTML 可以嵌入 evidence anchor ID 和短标签，但证据预览 JSON/图片必须通过 MyAgent 自己的鉴权 artifact endpoint 获取。
- bbox 应使用稳定的页面坐标，并在 preview 响应中明确 scale/DPI。图片渲染层再把坐标换算到像素并统一加 padding。
- 多页证据应暴露 `available_pages`，前端展示页签或连续页 gallery。单页证据可展示整页高亮图和局部裁剪图。
- 高亮框只是定位辅助，不是结论本身。最终结论仍绑定到 evidence anchor 和 review record。
- layout 文本匹配失败时，前端应展示声明页和失败原因，而不是隐藏“查看证据”入口。
- 浏览器内 skill 编辑风险较高。如实现，saved skill copy 必须由后端托管、限长、审计、版本化，并以引用记录到 run 中。不要允许用户提交任意工具规格、文件系统路径、shell、模型 ID 或 provider key。
- 人工 override 只能编辑 canonical compare path 上的窄字段，不能开放任意 JSON patch、HTML 注入或 prompt 改写。
- 前端仍应保持现有分层：API/token 逻辑在 `frontend/lib/task-api.ts`，任务状态和轮询在 `frontend/hooks/use-task-workspace.ts`，展示组件只接收归一化数据和回调。

## 已知坑点

- 不要把参考网页暴露出的运行日志当作安全样例。那些日志中出现过实现路径和第三方签名 URL，MyAgent 必须在入库和出 API 前脱敏。
- 不要要求 LLM 直接“画框”。正确做法是让 LLM 输出页码、条目、短摘录和 match hints，由后端根据 layout geometry 画框。
- Compare 生成不能只依赖自由 Markdown 渲染。应把 review 输出解析成 typed matrices，并校验必需字段后再发布最终产物。
- 不要只靠页码定位证据。应使用页码 + text needles/material names/excerpt 定位；失败时才回退到声明页整页图。
- 不要混用招标提取和投标评审 prompt。招标提取负责定义规则骨架；投标评审负责把一个投标人的材料应用到该骨架。
- 不要把图像预核验扩展成整份 PDF 视觉审查。它必须保持候选驱动和策略限额，否则成本和时延会失控。
- 追加投标文件或重跑阶段时，不要覆盖旧 run 产物。所有输出应 run-scoped、stage-aware。
- 不要发布坏的 evidence anchor。带 `data-evidence-anchor-id` 的 compare 单元格必须能解析到已知 anchor，否则应省略证据入口。
- 人工复核不能抹掉 AI baseline 和历史记录。评审人员需要同时知道模型原始判断和人工修改值。

## 关联代码路径

- `backend/app/main.py`：任务 API 边界，未来 PDF 上传、stage rerun、append bid、evidence preview API 可在此接入。
- `backend/app/storage.py`：run-scoped artifact、事件、路径安全和 artifact 访问。
- `backend/app/runner/core.py`：任务生命周期、路由、事件顺序和产物推广。
- `backend/app/agent/profiles.py`：现有后端托管的 bid multi-agent profile 和安全 subagent spec（目前仅有占位文档字符串）。
- `backend/app/tools/registry.py`：审计 workspace 文件工具注册，未来 PDF stage 不应绕过该边界。
- `frontend/app/page.tsx`：任务工作区挂载。
- `frontend/hooks/use-task-workspace.ts`：任务状态、轮询、上传和 artifact 操作。
- `frontend/lib/task-api.ts`：token-aware API 调用和 artifact fetch。
- `frontend/app/workspace-view.ts`：run 分组日志和 artifact 渲染。

注：分析逻辑分布在 `backend/app/tools/` 和 `backend/app/subagents/` 模块中，不再有独立的 `analysis.py` 或 `deep_agent_runtime.py` 文件。

未来若实现 PDF compare，可考虑新增：

- `backend/app/tender_pipeline.py`：阶段编排。
- `backend/app/pdf_ingest.py`：PDF 到 canonical document 的转换。
- `backend/app/tender_skills.py`：内置 skill 和 saved skill ref。
- `backend/app/evidence_anchor.py`：anchor 归一化与 preview resolver。
- `backend/app/compare_result.py`：compare matrices 与 HTML/JSON 产物生成。

## 关联测试路径

- `backend/tests/unit/agent/test_factory.py`：Agent 工厂和 profile 行为测试。
- `backend/tests/unit/tools/test_registry.py`：工具注册和安全边界测试。
- `backend/tests/integration/test_agent_build.py`：Agent 构建集成测试。
- `frontend/tests/state/test_task_state.test.ts`：日志、artifact、reasoning、orchestration payload 归一化。
- `frontend/tests/workspace/test_workspace_view.test.ts`：artifact 和 run card 渲染。
- `frontend/tests/upload/test_file_upload.test.ts`：上传过滤和校验行为。

未来建议补充：

- `backend/tests/analysis/`：招标/投标 Markdown parser、compare-result 校验。
- `backend/tests/storage/`：PDF artifact allowlist、preview image 访问。
- `backend/tests/security/`：签名 URL、绝对路径、provider key、原始文档泄漏。
- `backend/tests/api/`：PDF 上传、stage rerun、append bid、evidence preview、manual override API。
- `frontend/tests/workspace/`：证据预览 UI、compare artifact action、manual override 渲染。
- `frontend/tests/upload/`：PDF 上传槽位、skill ref、image policy 表单状态。

## 验证命令

仅文档改动：

```bash
git diff --check
```

后端行为改动：

```bash
cd backend
uv run pytest
uv run ruff check .
uv run mypy app tests
```

前端行为改动：

```bash
cd frontend
npm run typecheck
npm test
npm run lint
npm run build
```

## 回归风险

- PDF ingest 会引入大文件、长耗时和外部 provider 失败模式，风险高于当前 Markdown/JSON 流程。
- 证据预览图片即使不暴露文本，也可能展示敏感文档内容；preview endpoint 必须鉴权、run-scoped。
- ingest manifest 容易泄漏第三方签名 URL 和本地路径，必须在事件和 API 输出前脱敏。
- OCR/layout bbox 坐标会受缩放、旋转、裁剪和 DPI 影响，canonical JSON、渲染图片和 preview endpoint 必须使用一致坐标系。
- skill 编辑若不做 schema 检查和 run 级版本钉住，会破坏输出稳定性。
- manual override 若没有统一 overlay 源，可能导致 reviewed compare JSON、HTML、Excel 导出和历史记录不一致。
- append bid 后若下游失效不完整，会出现旧 compare 结果混入新投标人的问题。
- 独立 tender 页面如果绕过现有 task API/token/CORS 规则，会破坏 MyAgent 的本地优先安全边界。
