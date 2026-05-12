# Tender Workbench 项目工作流与实现逻辑拆解

生成时间：2026-05-06；脱敏更新：2026-05-12

本文基于一次已脱敏的 Tender Workbench 运行样本、页面结构和 API 返回形态整理，只保留稳定业务边界、接口形态和回归风险。

- 任务详情页形态：`/tender/runs/{run_id}`
- 新建分析页形态：`/tender/upload`
- 任务 API 形态：`/api/tender/runs/{run_id}`
- 运行信息、执行记录、产物清单、compare 结果 JSON/HTML、skill 内容与 evidence preview API

说明：本文不保留客户项目名、真实运行编号、输入文件路径、外部域名、终端会话名、单次令牌消耗或其他一次性运行细节。对后端实现的描述分为两类：

- 已确认：来自页面 JS、API 响应、运行记录、产物清单、skill 内容、预览接口返回。
- 推断：根据已确认数据反推后端模块职责和实现方式。推断处会明确说明。

## 1. 一句话结论

这个项目不是把多份 PDF 直接丢给 AI 做一次性对比，而是先把招标文件变成统一的评审骨架，再把每份投标文件按同一骨架分别评审成结构化 Markdown，最后用确定性程序把各投标人的结果对齐成横向矩阵、风险列表、待澄清事项和 compare 页面。

证据“画框”也不是让 AI 在图上直接画框。AI 主要负责输出评审结论、证据页码、文本线索和视觉核验结论；后端再用 MinerU/OCR 的 `layout.json` 中的文本块坐标去定位原 PDF 页面，生成带高亮框的整页图和局部裁剪图。如果文本命不中，就退化为展示声明页整页图。

## 2. 脱敏样本运行的关键事实

任务信息形态：

| 项 | 值 |
|---|---|
| run_id | `{run_id}` |
| 项目名 | `{project_name}` |
| 状态 | `completed` |
| 当前阶段 | `compare_page` |
| 最新消息 | `compare 页面生成完成` |
| 产物数 | 90 |
| 事件数 | 101 |
| 阶段数 | 9 |

输入配置：

| 项 | 值 |
|---|---|
| 招标文件 | `{run_dir}/inputs/tender/{tender_file}` |
| 投标文件 | 3 份：`bid-01-pdf`、`bid-02-pdf`、`bid-03-pdf` |
| 招标评审模型 | `gpt-5.4` |
| 投标评审模型 | `gpt-5.4` |
| 图像预核验模型 | `gpt-5.4-mini` |
| 图像策略 | `medium` |
| tender skill | `tender-review builtin/default` |
| bid skill | `bid-review builtin/default` |
| pdf image skill | `pdf-image-check builtin/default` |

`medium` 图像策略在 summary 中展开为：

```json
{
  "max_candidates": 20,
  "include_product_brochure": true,
  "dpi_ladder": [300, 400],
  "retry_only_unclear": true,
  "ocr_first": true,
  "max_long_edge_px": 4200,
  "max_image_pixels": 12000000
}
```

## 3. 总体流水线

运行记录显示的核心阶段如下：

| 阶段 | 作用 | 产物重点 |
|---|---|---|
| `tender_ingest` | 解析招标文件 | raw copy、MinerU zip、`layout.json`、canonical JSON、full markdown |
| `tender_review` | 从招标文件提取评标辅助表骨架 | prompt、response、`review_markdown.md`、events |
| `bid_ingest:bid-01` | 解析第 1 份投标文件 | raw copy、MinerU zip、`layout.json`、canonical JSON |
| `bid_review:bid-01` | 评审第 1 份投标文件 | 图像候选、图像证据、bid prompt、bid review markdown |
| `bid_ingest:bid-02` | 解析第 2 份投标文件 | 同上 |
| `bid_review:bid-02` | 评审第 2 份投标文件 | 同上 |
| `bid_ingest:bid-03` | 解析第 3 份投标文件 | 同上 |
| `bid_review:bid-03` | 评审第 3 份投标文件 | 同上 |
| `compare_page` | 生成最终对比结果 | `compare_result.json`、`compare_result.html` |

运行日志中的顺序可以概括为：

```text
上传并保存输入文件
-> 招标文件和投标文件并行提交 MinerU 解析
-> 生成每份文件的 canonical JSON 和页级 Markdown
-> 用 tender-review skill 生成招标侧评标骨架
-> 为每份投标文件生成高优先级图像候选
-> 用 pdf-image-check skill 做最小必要视觉核验
-> 把视觉核验附录塞回投标页级 Markdown
-> 用 bid-review skill 对每份投标文件做单独评审
-> 汇总所有 bid_review markdown，生成 compare JSON
-> 渲染 compare HTML、Excel、证据锚点预览接口
```

从时间看，PDF ingest 基本并行执行。招标评审完成后，三份投标文件评审在状态记录中呈现为依次完成：

| 阶段 | UTC 时间 | 耗时 |
|---|---:|---:|
| `tender_review` | 02:18:00 到 02:22:03 | 243.481s |
| `bid_review:bid-01` | 02:22:03 到 02:28:39 | 395.248s |
| `bid_review:bid-02` | 02:28:39 到 02:34:50 | 370.9s |
| `bid_review:bid-03` | 02:34:50 到 02:41:12 | 382.052s |

API 时间是 UTC。按 Asia/Shanghai 计算，上述运行大约是 2026-05-06 10:16 到 10:41。

## 4. 上传页是怎么组织任务的

`/tender/upload` 的前端分成三步。

### Step 1：基础信息与文件

用户输入：

- 项目名称，字段名：`project_name`
- 招标文件，字段名：`tender_pdf`
- 多个投标文件，字段名：`bid_pdfs`

前端允许动态增加投标文件槽位。提交时使用 `FormData` 发起：

```text
POST /api/tender/runs
```

### Step 2：模型与图像策略

前端可选：

- 招标文件评审模型：`gpt-5.4` 或 `gpt-5.4-mini`
- 投标文件评审模型：`gpt-5.4` 或 `gpt-5.4-mini`
- 图像核验策略：`low`、`medium`、`high`、`original`

提交字段：

```text
tender_model
bid_model
image_evidence_policy_preset
```

图像策略影响：

- 候选页数量上限
- PDF 页面渲染 DPI
- 是否先 OCR 再决定是否升 DPI
- 最大图片像素和长边控制
- 是否包含产品彩页等图像敏感材料

### Step 3：Skill 版本

上传页有三类 skill：

| 上传页标签 | family | 作用 | contract_id |
|---|---|---|---|
| 招标文件抽取 | `tender-review` | 从招标文件抽取评标辅助表骨架 | `tender_review_markdown.v1` |
| 投标文件评审 | `bid-review` | 按招标骨架评审单个投标文件 | `bid_review_markdown.v1` |
| PDF 图像核验 | `pdf-image-check` | 对高价值候选页做视觉核验 | `pdf_image_check.v1` |

前端使用这些接口：

```text
GET    /api/tender/skills
GET    /api/tender/skills/content?family=...&source=...&version_id=...
POST   /api/tender/skills/save-copy
DELETE /api/tender/skills
```

当前线上 catalog 只有三个 builtin/default，没有 saved 副本。

提交任务时，前端把版本选择写入：

```text
tender_skill_source
tender_skill_version
bid_skill_source
bid_skill_version
pdf_image_skill_source
pdf_image_skill_version
```

这意味着每次 run 都会记录当时用的是哪个 skill 版本。后续查看“运行信息”时能复盘当时的规则版本。

## 5. 三个 skill 分别负责什么

### 5.1 `tender-review`：把招标文件变成评审骨架

这个 skill 的任务是从招标文件中提取固定结构的中文 Markdown。重点不是总结招标文件，而是建立后续评审要用的“条目骨架”。

它优先找：

- 资格审查响应表
- 符合性审查响应表
- 投标人须知前附表
- 评分标准表
- 技术需求表、服务要求表、响应/偏离表

输出固定章节：

```text
一、项目与评标框架
二、资格审查辅助表
三、符合性审查辅助表
四、价格评分表
五、技术评分表
六、商务评分表
七、响应/偏离/技术响应逐项提取
八、特殊符号、支持资料与澄清修正规则
```

关键设计点：

- 先建立条目骨架，再填字段。
- 骨架一旦建立，后续默认不新增条目，除非满足“表外补充”的严格条件。
- `★`、`▲` 等符号必须保留。
- 没有明确证据要求或后果时，不能脑补。

这一步的输出是后面所有投标文件横向比较的基准。

### 5.2 `pdf-image-check`：先做小范围视觉核验

这个 skill 不审完整投标文件，只检查候选页。

输入是候选 JSON，每个候选包含：

- `candidate_id`
- `target_item`
- `focus_question`
- `local_pdf_page_image_path`
- `expected_visual_signals`
- `page_titles`
- `page_text_excerpt`

它的输出是结构化 JSON：

```json
{
  "candidate_id": "...",
  "inspection_status": "pass | fail | needs_review | image_unreadable",
  "confidence": "high | medium | low",
  "visual_fact": "...",
  "recommended_review_note": "..."
}
```

这次 `bid-01` 的图像候选例子是信用截图。候选页为 P21，问题是判断“重大税收违法失信主体”查询结果是否明确显示无记录。图像核验结果为 `pass`，并生成了可被主评审引用的短句。

这个 skill 的定位很关键：它只解决 OCR 不稳的视觉事实，例如截图结果、印章、签字、证照有效期、保证金回单状态等。它不做最终合格性判断。

### 5.3 `bid-review`：把单份投标文件评审成同构结果

这个 skill 的输入顺序是：

1. 招标侧 `review_markdown.md`
2. 投标文件页级展开 Markdown
3. 页级 Markdown 末尾的“高优先级图像证据预抽取”附录

输出固定章节：

```text
一、项目信息
二、资格审查
三、符合性审查
四、价格评审
五、技术评分初评
六、商务评分初评
七、响应/偏离逐项核对
八、需澄清/待补证据事项
九、主要风险与可能触发否决的事项
十、总体判断
```

关键规则：

- 二到七章必须沿用招标侧骨架，不允许新增、改名、合并、拆分。
- 找不到材料时标 `未见响应`。
- 提到但证据不足时标 `待核实`。
- 明确冲突时标 `不通过` 或 `负偏离`。
- 单份投标文件无法完成价格横向比较时，价格结论通常是 `待横向比较`。
- 图像核验 `pass` 可以作为补充视觉证据，`needs_review` 或 `image_unreadable` 保守处理。

这就是为什么多份投标文件能比较：它们不是自由文本报告，而是同一招标骨架下的同构 Markdown。

## 6. “上传投标文件可以比较”的核心实现逻辑

比较能力来自四层规范化。

### 第一层：PDF 规范化

每份 PDF 或文档先通过 MinerU 解析为：

- raw `layout.json`
- canonical JSON
- 页级 Markdown
- 页面标题、表格、段落、页码、图片等结构

这样后续不直接面对原始 PDF，而是面对可检索、可引用页码的结构化文本。

### 第二层：招标文件规范化

`tender-review` 把招标文件提取成评审骨架。这个骨架定义了后续每份投标文件必须回答哪些问题。

例如本项目的响应/偏离逐项核对有 17 项。每个投标人都必须围绕这些条目输出结论。

### 第三层：投标文件同构评审

每份投标文件分别用 `bid-review` 评审，输出同样的章节、条目、字段：

- 结论
- 投标响应摘录
- 对应材料
- 评审说明
- 证据页码
- 原始依据
- 风险和待澄清事项

### 第四层：确定性 compare builder

后端再把多份 `bid_review_markdown.md` 解析成结构化对象，并按共同条目对齐：

- `qualification_matrix`
- `conformity_matrix`
- `price_matrix`
- `technical_matrix`
- `business_matrix`
- `deviation_matrix`
- `risk_profiles`
- `bidder_watchlists`
- `key_differences`
- `focus_points`

最终生成：

- `compare_result.json`
- `compare_result.html`
- `review-analysis.xlsx`

所以实际比较的是“同一招标骨架下各投标人的结构化评审字段”，不是原始 PDF 的全文相似度。

## 7. compare 页面怎么生成

`compare_result.json` 的顶层结构是：

```text
schema_version
evidence_anchor_schema_version
generated_at
project
inputs
bidders
comparison
evidence_anchors
```

其中 `comparison` 包含：

```text
summary_rows
bidder_snapshots
bidder_display_items
bidder_display_metrics
bidder_scoreboards
price_overview
dashboard
executive_briefs
qualification_matrix
conformity_matrix
price_matrix
technical_matrix
business_matrix
deviation_matrix
risk_profiles
bidder_watchlists
key_differences
focus_points
```

本次结果中：

- 投标人数量：3
- `qualification_matrix`：7 项
- `conformity_matrix`：11 项
- `price_matrix`：1 项
- `technical_matrix`：1 项
- `business_matrix`：1 项
- `deviation_matrix`：17 项
- `evidence_anchors`：135 个

compare HTML 只是把这些结构渲染成页面。页面上的“只显示有问题”“技术响应筛选”“查看证据”“人工修改”都是前端增强。

## 8. 证据锚点和“画框”的真实机制

### 8.1 证据锚点是什么

compare JSON 里每个可追溯单元格都有一个 `evidence_anchor`。典型结构如下：

```json
{
  "anchor_id": "bid-01-pdf:deviation-check:deviation-checks:deviation-12",
  "bidder_name": "上海康堪生物科技有限公司",
  "bid_document_id": "bid-01-pdf",
  "source_kind": "deviation_check",
  "section_key": "deviation_checks",
  "item_title": "二.6",
  "pages": [49, 54, 29],
  "primary_page": 49,
  "source_refs": {
    "source_pdf_name": "bid-01-pdf",
    "source_json_name": "layout.json"
  },
  "match_hints": {
    "preferred_match_mode": "table_row",
    "text_needles": [
      "二.6",
      "胶片大小可根据样本的大小进行调节；调节范围≥4档",
      "胶片大小可根据样本的大小进行调节；调节范围：4档。"
    ],
    "excerpt": "胶片大小可根据样本的大小进行调节；调节范围：4档。"
  }
}
```

它不是图片，也不是框，而是“如何回到原始 PDF 找证据”的索引。

### 8.2 点击“查看证据”时发生什么

compare HTML 中，单元格会带：

```html
data-evidence-anchor-id="..."
```

点击后，前端调用：

```text
GET /api/tender/runs/{run_id}/evidence-anchors/{anchor_id}/preview
GET /api/tender/runs/{run_id}/evidence-anchors/{anchor_id}/preview/page
GET /api/tender/runs/{run_id}/evidence-anchors/{anchor_id}/preview/crop
```

`preview` JSON 返回：

```text
page_no
scale
focus_bbox
crop_bbox
image_size
crop_size
page_image_url
crop_image_url
resolved.match_mode
resolved.matched_text
available_pages
declared_pages
```

页面再把 `page_image_url` 和 `crop_image_url` 塞进两个 `<img>` 中显示。

### 8.3 框是谁画的

从 API 形态看，后端证据 resolver 负责画框或裁剪。

推断实现步骤：

```text
1. 根据 anchor_id 找到 evidence_anchor。
2. 读取 anchor.source_refs 指向的 raw layout.json 和原始 PDF。
3. 在 declared_pages / primary_page 中查找 match_hints.text_needles。
4. 根据 preferred_match_mode 选择匹配策略：
   - line：找文本行
   - table_row：找表格行或近邻块
   - declared_page：找不到时只展示声明页
5. 从 layout.json 取命中文本块的 bbox。
6. 按渲染 scale 把 PDF 坐标转换成图片像素坐标。
7. 生成整页 PNG，并在 focus_bbox 上画高亮框。
8. 根据 crop_bbox 裁剪局部图。
9. 返回 preview JSON 和两张 PNG。
```

这说明“画框”主要依赖 OCR/layout 坐标，而不是 AI 自己输出坐标。AI 的职责是给出证据页码、摘录、关键词和匹配线索。

### 8.4 命中和未命中的例子

命中例子：`bid-01-pdf:deviation-check:deviation-checks:deviation-12`

预览 API 返回：

```json
{
  "status": "matched",
  "match_mode": "line",
  "confidence": 0.5,
  "page_no": 49,
  "focus_bbox": [116, 423, 315, 460],
  "crop_bbox": [92, 399, 339, 484],
  "matched_text": "胶片使用宽度可进行4档设定..."
}
```

这类结果会有整页高亮图和局部裁剪图。

未命中例子：`bid-02-pdf:deviation-check:deviation-checks:deviation-12`

预览 API 返回：

```json
{
  "status": "declared_page_fallback",
  "match_mode": "declared_page",
  "confidence": 0,
  "page_no": 30,
  "focus_bbox": null,
  "crop_bbox": null,
  "reason": "声明主证据页 P30 未命中页内文本，回落展示声明页整页图"
}
```

这类结果不会有精确框，只会展示声明页整页图。

### 8.5 为什么有时框不准

框不准通常不是 AI “不会画”，而是定位链条某一环不稳定：

- AI 给的页码是对的，但摘录与 OCR 文本不完全一致。
- PDF 是扫描件，OCR 文本和视觉内容有差异。
- 表格跨行、跨页或被拆成多个文本块。
- `preferred_match_mode=table_row` 但 layout 中表格结构不完整。
- 图片型证据没有可匹配文本，只能回落到整页。
- 页码映射可能存在封面、目录、扫描页偏移。

可改进方式：

- 在 evidence_anchor 中保存更多 `text_needles`，包括短关键词和原始摘录。
- 对表格行做 fuzzy match，而不是只按连续文本匹配。
- 保存 `locator_hint.matched_by`，优先匹配 excerpt。
- 对视觉证据允许使用 image check 输出的关键区域描述来辅助定位。
- 对常见证照、截图、回单建立专门 locator。

## 9. 运行页面的调试能力

任务详情页前端暴露了这些能力。

### 9.1 分视图加载

```text
GET /api/tender/runs/{run_id}?view=overview
GET /api/tender/runs/{run_id}?view=result
GET /api/tender/runs/{run_id}?view=info
GET /api/tender/runs/{run_id}/artifacts
```

`overview` 用于进度、最近事件和阶段状态。

`result` 用于 compare 摘要、结果页入口、Excel 下载。

`info` 用于 summary、模型、skill 版本、runtime log 信息。

`artifacts` 用于文档、日志、prompt、response、intermediate 文件预览。

### 9.2 阶段重跑

前端支持以下阶段重新执行：

```text
tender_ingest
tender_review
compare_page
bid_ingest:{bid_key}
bid_review:{bid_key}
```

接口：

```text
POST /api/tender/runs/{run_id}/stages/{stage_key}/rerun
```

前端提示中透露了依赖关系：

| 重跑阶段 | 影响范围 |
|---|---|
| `tender_ingest` | 重跑招标解析，并刷新后续评审与 compare |
| `tender_review` | 重跑招标评审，并刷新所有投标评审与 compare |
| `bid_ingest:*` | 重跑当前投标解析，并刷新该投标评审与 compare |
| `bid_review:*` | 重跑当前投标评审，并刷新 compare |
| `compare_page` | 只重跑 compare 页面生成 |

### 9.3 追加投标文件

任务完成后仍可追加投标文件：

```text
POST /api/tender/runs/{run_id}/bids
```

追加后页面会进入刷新状态，重新生成 compare 结果。

### 9.4 人工复核和 AI 协同评审

compare 页面加载了 `compare-enhance.js`，其中包含人工修改能力：

```text
GET  /api/tender/runs/{run_id}/reviewed-compare-result
POST /api/tender/runs/{run_id}/manual-review-override
GET  /api/tender/runs/{run_id}/manual-review-overrides
GET  /api/tender/runs/{run_id}/manual-review-history
```

这说明系统把 AI 结果视为初稿，允许人工修改结论、分值和评审说明，并记录原因与历史。

## 10. 产物目录设计

单次 run 的目录结构大致是：

```text
runs/{run_id}/
  inputs/
    tender/
    bids/
  stages/
    tender_ingest/
      raw/
      canonical/
      run_manifest.json
    tender_review/
      review_markdown.prompt.md
      review_markdown.md
      responses/
      logs/
    bidders/
      bid-01/
        ingest/
          raw/
          canonical/
        review/
          priority_image_evidence/
            candidates.json
            priority_image_evidence.json
            priority_image_evidence.md
            page_images/
          bid_canonical_markdown.md
          bid_review.prompt.md
          bid_review_markdown.md
          responses/
          logs/
      bid-02/
      bid-03/
    compare/
      compare_result.json
      compare_result.html
  summary.json
  pipeline_status.json
  pipeline_events.jsonl
  artifacts_manifest.json
  runtime_logs.json
```

这种目录设计有几个好处：

- 每个阶段输入输出可追溯。
- prompt、response、stderr、event summary 都保留，方便复盘。
- 解析、评审、compare 分离，便于单阶段重跑。
- 新增投标文件时，可以复用已有招标侧产物。
- evidence anchor 可以回溯到原始 PDF 和 raw `layout.json`。

## 11. 如果我要复刻这个项目，会拆成哪些模块

推断的后端模块如下：

```text
web_auth.py
  - 登录、cookie session

web_runs.py
  - POST /runs 创建任务
  - GET /runs 查询任务
  - GET /runs/{id} 查询任务详情
  - POST /runs/{id}/bids 追加投标
  - POST /runs/{id}/stages/{stage}/rerun 重跑阶段

skill_registry.py
  - builtin skills
  - saved copies
  - version refs

pipeline_runner.py
  - 创建 run_dir
  - 写 summary/status/events/artifacts
  - 调度各阶段

ingest_mineru.py
  - 上传 PDF/文档给 MinerU
  - polling batch status
  - 下载 zip/layout.json
  - 生成 canonical JSON 和 full.md

tender_review.py
  - 读取 tender-review skill
  - 拼 prompt
  - 调模型生成 review_markdown.md

image_evidence.py
  - 从 bid canonical 中抽高优先级候选页
  - 渲染 PDF 页为 PNG
  - 调 pdf-image-check skill
  - 生成 priority_image_evidence.md

bid_review.py
  - 读取 bid-review skill
  - 拼招标 review + 投标页级 markdown + 图像附录
  - 调模型生成 bid_review_markdown.md

compare_builder.py
  - 解析 tender review 和 bid reviews
  - 对齐各投标人的条目
  - 生成 matrices、dashboard、focus_points、risk profiles
  - 生成 evidence_anchors

evidence_resolver.py
  - 根据 anchor_id、layout.json、PDF 定位证据
  - 生成 focus_bbox、crop_bbox、page/crop PNG

artifact_server.py
  - 产物预览、下载、权限控制

manual_review.py
  - 人工 override、history、reviewed compare result
```

## 12. 你可能会问的问题

### Q1：为什么要先评审招标文件？

因为招标文件定义了“应该比较什么”。如果不先提取招标侧条目，AI 很容易对每份投标文件各说各话，最后无法横向对齐。

### Q2：为什么投标评审要逐份做，而不是一次比较三份？

逐份评审可以让每份投标文件在同一招标骨架下独立形成证据链。这样更容易追溯、重跑和定位错误。横向比较放在最后用程序完成，稳定性更高。

### Q3：图像核验为什么独立成 skill？

因为大多数内容 OCR 足够，只有截图、签章、证照、回单这类视觉事实需要看原图。独立成 skill 可以控制 token 和成本，也能把视觉判断限制在明确候选页上，避免扩扫整份 PDF。

### Q4：为什么 compare 页面能点开证据？

因为 compare builder 在生成每个结果单元格时，附带了 `evidence_anchor`。这个 anchor 记录投标文件、页码、匹配关键词、原始 PDF 和 layout JSON 的引用。前端点击后调用后端 preview API 动态定位。

### Q5：AI 有没有直接输出坐标？

从现有数据看，没有。`pdf-image-check` 输出的是视觉事实和状态，不输出 bbox。`bid-review` 输出的是 Markdown 结论和证据页码。bbox 来自 evidence resolver 对 `layout.json` 的文本块匹配和 PDF 渲染。

### Q6：为什么有些证据只有整页，没有局部框？

当 resolver 在声明页找不到匹配文本时，会返回 `declared_page_fallback`，`focus_bbox` 和 `crop_bbox` 为 `null`。这种情况只能展示整页，让人工核对。

### Q7：如何调试一个错误结论？

建议顺序：

1. 打开 compare 页面对应单元格，点“查看证据”。
2. 看是否命中 bbox。如果没有 bbox，说明 locator 没命中，不一定是评审错。
3. 在任务页“执行记录”里打开对应 bid 的 `bid_review.prompt.md` 和 `bid_review_markdown.md`。
4. 打开该 bid 的 `priority_image_evidence.md`，确认图像预核验有没有影响结论。
5. 打开 canonical 或 raw `layout.json`，看 OCR 是否读错。
6. 如果是规则问题，复制并修改对应 skill，然后重跑对应阶段。

### Q8：改哪个 skill 才能修问题？

| 问题类型 | 优先改 |
|---|---|
| 招标条目漏提、骨架错 | `tender-review` |
| 单份投标文件判断错、字段写法不稳 | `bid-review` |
| 截图、印章、证照、回单视觉判断错 | `pdf-image-check` |
| compare 页面显示/排序/矩阵聚合错 | 后端 compare builder 或前端 compare HTML |
| 证据框错位或找不到 | evidence resolver，不一定是 skill |

### Q9：为什么 token 消耗这么高？

因为招标评审和每份投标评审都读取了较长的页级 Markdown，并要求固定结构输出。典型高消耗阶段包括 `tender_review` 和每个 `bid_review:*`。长期知识包只记录消耗模式和优化方向，不保留单次令牌消耗明细。

可优化方向：

- 更强的 canonical 摘要层。
- 先由程序抽表，再让 AI 只判疑难项。
- 对投标文件按招标骨架检索相关页，而不是全量页级 Markdown。
- 对重复的招标骨架和 skill 做缓存。

### Q10：这个系统可靠性的边界在哪里？

可靠部分：

- 阶段化产物可追溯。
- 招标骨架统一，横向对齐稳定。
- prompt、response、events、runtime logs 等脱敏运行证据都可复盘。
- 人工 override 有历史记录。

风险部分：

- OCR 质量会影响所有后续判断。
- AI 输出 Markdown 的结构如果漂移，解析器可能受影响。
- evidence resolver 依赖文本匹配，图像型证据不一定能精确框。
- AI 可能把页码、材料名称或冲突关系理解错，需要人工复核。
- 投标合格性是高风险场景，最终应由评审人员确认。

## 13. 最小实现伪代码

```python
def create_run(project_name, tender_file, bid_files, config):
    run = init_run_dir(project_name)
    save_inputs(run, tender_file, bid_files)
    record_skill_refs(run, config.skill_refs)
    record_image_policy(run, config.image_policy)

    tender_ingest_job = submit_mineru(tender_file)
    bid_ingest_jobs = [submit_mineru(file) for file in bid_files]

    tender_canonical = wait_and_build_canonical(tender_ingest_job)
    bid_canonicals = [wait_and_build_canonical(job) for job in bid_ingest_jobs]

    tender_review = run_llm(
        skill="tender-review",
        model=config.tender_model,
        inputs=[tender_canonical.full_markdown],
    )

    bid_reviews = []
    for bid in bid_canonicals:
        candidates = select_priority_image_candidates(bid, config.image_policy)
        visual_evidence = run_image_skill(
            skill="pdf-image-check",
            model=config.image_model,
            candidates=candidates,
        )
        bid_markdown = build_bid_markdown(bid, visual_evidence)
        bid_review = run_llm(
            skill="bid-review",
            model=config.bid_model,
            inputs=[tender_review.markdown, bid_markdown],
        )
        bid_reviews.append(bid_review)

    compare = build_compare_result(tender_review, bid_reviews)
    compare.evidence_anchors = build_evidence_anchors(compare, bid_canonicals)
    render_compare_html(compare)
    export_excel(compare)
    finalize_run(run)
```

## 14. 复盘这次运行的项目结果

这次 compare 摘要显示三个投标人中：

- 上海康堪生物科技有限公司：总体判断为 `建议判定不通过`，符合性审查有不通过风险。
- 上海希赞医疗科技有限公司：总体判断为 `存在可能触发否决事项`，有技术负偏离和资格风险。
- 上海熹楚医疗器械有限公司：存在保证金、主体名称、技术参数冲突等待核实或风险项。

页面给出的 focus points 是：

```text
1. 整体盖章、签署与装订形式是否满足招标文件要求。
2. ★ 条款支持页与响应表是否逐项闭合。
3. 一般参数负偏离是否影响技术评分或实质性响应判断。
4. 价格评审仍需结合全部有效投标人做横向比较，当前页面仅反映单份投标文件口径。
```

这进一步说明 compare 页面是评审辅助工具，不是最终自动定标工具。
