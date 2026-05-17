# 09 标准答案

## 自测题答案

1. 招标文件提供规则和要求；投标文件提供各投标人的响应、报价、方案和证明材料。分析通常要用招标要求作为基准，再横向比较多个投标文件。
2. 围串标判断需要法律、事实和上下文支持。系统只能基于文档线索提示风险、证据和不确定性，不能替代正式法律结论。
3. 稳定业务规则优先写入 `asset/bid_analysis_workflow_knowledge_pack.md`；如果是平台通用边界，则写入 `asset/deepagents_platform_knowledge_pack.md`。
4. PDF 原文可能很大、结构复杂且包含敏感内容。正确方向是先 ingest 成 canonical/page-level 结构和安全中间产物，再按证据范围读取、评审和生成 artifact。

## 练习观察点

一份投标文件只能做单文档检查，不能做“多投标人相似性对比”。因此最小规则要求至少两份 bid 文档。

如果未来仓库新增 `backend/app/tender_pipeline.py`、`pdf_ingest.py` 或 `compare_result.py`，本章练习会提醒更新资料。那时应把“需要结合源码进一步确认”的部分改成真实源码讲解。
