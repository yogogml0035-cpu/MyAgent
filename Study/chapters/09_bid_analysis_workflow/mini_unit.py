from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Document:
    name: str
    text: str


def classify_document(doc: Document) -> str:
    text = doc.text
    if "招标公告" in text or "招标文件" in text:
        return "tender"
    if "投标函" in text or "报价表" in text or "投标人" in text:
        return "bid"
    return "unknown"


def requires_at_least_two_bidders(documents: list[Document]) -> bool:
    bid_count = sum(1 for doc in documents if classify_document(doc) == "bid")
    return bid_count >= 2


def detect_shared_phrase_risk(documents: list[Document], phrase: str) -> dict:
    bid_docs = [doc for doc in documents if classify_document(doc) == "bid"]
    matched = [doc.name for doc in bid_docs if phrase in doc.text]
    return {
        "risk": len(matched) >= 2,
        "phrase": phrase,
        "matched_documents": matched,
    }


def assert_source_contracts() -> None:
    bid_pack = (REPO_ROOT / "asset/bid_analysis_workflow_knowledge_pack.md").read_text(
        encoding="utf-8"
    )
    tender_pack = (REPO_ROOT / "asset/tender_workflow_breakdown.md").read_text(
        encoding="utf-8"
    )
    resources = (REPO_ROOT / "backend/app/execution/resources.py").read_text(encoding="utf-8")
    runner = (REPO_ROOT / "backend/app/runner/core.py").read_text(encoding="utf-8")

    for keyword in ["招标文件", "投标文件", "Compare", "证据锚点"]:
        assert keyword in bid_pack, f"业务知识包应提到 {keyword}"
    assert "tender-review" in tender_pack
    assert "bid-review" in tender_pack
    assert "read_resource_text" in resources
    assert "read_resource_table" in resources
    assert "RESOURCE_TOOL_SYSTEM_PROMPT" in runner

    # 当前源码没有这些完整生产模块。若未来新增，本章应同步更新。
    planned_modules = [
        REPO_ROOT / "backend/app/tender_pipeline.py",
        REPO_ROOT / "backend/app/pdf_ingest.py",
        REPO_ROOT / "backend/app/compare_result.py",
    ]
    assert not any(path.exists() for path in planned_modules), (
        "发现 PDF compare 生产模块已出现，请更新本章：不要再说它只是未来实现边界"
    )


if __name__ == "__main__":
    docs = [
        Document("招标.md", "本项目招标文件要求供应商提交技术方案。"),
        Document("A投标.md", "投标人A提交投标函。技术方案：完全响应全部条款。"),
        Document("B投标.md", "投标人B提交报价表。技术方案：完全响应全部条款。"),
    ]

    assert requires_at_least_two_bidders(docs)
    risk = detect_shared_phrase_risk(docs, "完全响应全部条款")
    assert risk["risk"] is True
    assert risk["matched_documents"] == ["A投标.md", "B投标.md"]
    assert_source_contracts()

    print(risk)
    print("OK: 你已经理解招投标对比分析的最小业务规则。")
