from __future__ import annotations

import itertools
import re
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from functools import partial
from html import escape
from pathlib import Path
from typing import Any

from .model_provider import ModelProvider
from .runtime import CancellationController
from .storage import TaskStorage
from .tools import WorkspaceTools

Emit = Callable[[str, str, dict[str, Any] | None], None]


@dataclass(frozen=True)
class MarkdownDocument:
    filename: str
    role: str
    bidder_name: str | None
    text: str
    lines: list[str]


@dataclass(frozen=True)
class SubAgentSpec:
    agent_id: str
    category: str
    label: str
    prompt: str
    tools: list[str]
    input_files: list[str]


BID_CATEGORIES = [
    "quotation_similarity",
    "technical_text_similarity",
    "template_traces",
    "shared_entities",
    "requirement_deviations",
    "metadata_clues",
    "common_deviations",
]

SUBAGENT_TOOL_NAMES = ["list_dir", "read_file", "full_text_search", "tavily_search"]
MAX_SIMILARITY_PARAGRAPHS_PER_DOCUMENT = 120
MAX_SIMILARITY_COMPARISONS_PER_PAIR = 20_000
TENDER_FILENAME_MARKERS = ("tender", "招标", "采购文件", "需求书")
PRICE_CONTEXT_PATTERN = re.compile(
    r"(报价|总价|投标价|价格|金额|费用|单价|分项|合价|人民币|预算|费率|折扣|税率|元|万元|%)"
)
NON_PRICE_CONTEXT_PATTERN = re.compile(
    r"(电话|手机|联系方式|联系人|日期|时间|年|月|日|页码|页|章节|第\s*\d+\s*[章节条款]|工期|天)"
)
TENDER_HEADING_PATTERNS = (
    re.compile(
        r"^\s*#*\s*(?:[\w\-\s（）()]*项目)?\s*(?:招标文件|采购文件|需求书)\s*$", re.IGNORECASE
    ),
    re.compile(r"^\s*#*\s*tender document\s*$", re.IGNORECASE),
)


CATEGORY_LABELS = {
    "quotation_similarity": "Quotation / bill similarity",
    "technical_text_similarity": "Technical proposal copied sections",
    "template_traces": "Identical typos, formatting, or template traces",
    "shared_entities": "Repeated people, companies, places, or contacts",
    "requirement_deviations": "Common deviations from tender requirements",
    "metadata_clues": "Timestamp, author, or OCR metadata clues",
    "common_deviations": "Repeated abnormal response patterns",
}


def run_bid_analysis(
    *,
    task_id: str,
    uploads: list[Path],
    task_message: str,
    model: str,
    model_provider: ModelProvider,
    storage: TaskStorage,
    controller: CancellationController,
    workspace_tools: WorkspaceTools,
    emit: Emit,
) -> dict[str, Any]:
    cancel_event = controller.event
    documents = load_markdown_documents(uploads)
    classified = classify_documents(documents)
    storage.write_json(task_id, "artifacts/input-manifest.json", render_input_manifest(classified))
    plan = build_execution_plan(task_message, classified)
    storage.write_json(task_id, "plan.json", plan)
    storage.write_text(task_id, "artifacts/task-plan.md", render_plan_markdown(plan))
    emit("plan_created", "Execution plan generated", {"plan": plan})

    if cancel_event.is_set():
        raise CancelledError()

    bidder_docs = [doc for doc in classified if doc.role == "bidder"]
    tender_docs = [doc for doc in classified if doc.role == "tender"]
    if len(bidder_docs) < 2:
        raise NeedsInputError(
            "At least two Markdown bidder documents are required for comparison.",
            {"minimum_bidder_documents": 2, "current_bidder_documents": len(bidder_docs)},
        )

    reports: list[dict[str, Any]] = []
    specs = build_subagent_specs(task_message, classified)
    max_workers = min(4, len(BID_CATEGORIES))
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures: dict[Future, SubAgentSpec] = {}
        attempts: dict[Future, int] = {}
        pending: set[Future] = set()
        for spec in specs:
            storage.write_json(task_id, f"subagents/{spec.category}-task.json", asdict(spec))
            worker = SubAgentWorker(
                spec=spec,
                tender_docs=tender_docs,
                bidder_docs=bidder_docs,
                tools=workspace_tools,
                model=model,
                model_provider=model_provider,
                controller=controller,
                emit=emit,
            )
            future = pool.submit(worker.run)
            controller.register_future(future)
            futures[future] = spec
            attempts[future] = 0
            pending.add(future)
        emit(
            "subagents_started",
            "Concurrent sub-agent analysis started",
            {"count": len(pending), "max_workers": max_workers},
        )

        while pending:
            if cancel_event.is_set():
                for future in pending:
                    future.cancel()
                raise CancelledError()
            done, pending = wait(pending, timeout=0.1, return_when=FIRST_COMPLETED)
            for future in done:
                controller.unregister_future(future)
                spec = futures[future]
                category = spec.category
                if future.cancelled():
                    raise CancelledError()
                try:
                    report = future.result()
                except Exception as exc:  # retry once with a narrower prompt-equivalent path.
                    if cancel_event.is_set():
                        raise CancelledError()
                    if attempts[future] >= 1:
                        raise
                    emit(
                        "subagent_retry",
                        f"Retrying {CATEGORY_LABELS[category]} after failure",
                        {"category": category, "error": str(exc)},
                    )
                    retry_spec = SubAgentSpec(
                        agent_id=f"{spec.agent_id}-retry",
                        category=spec.category,
                        label=spec.label,
                        prompt=spec.prompt
                        + "\nRetry instruction: narrow the evidence search and return only supported findings.",
                        tools=spec.tools,
                        input_files=spec.input_files,
                    )
                    retry_worker = SubAgentWorker(
                        spec=retry_spec,
                        tender_docs=tender_docs,
                        bidder_docs=bidder_docs,
                        tools=workspace_tools,
                        model=model,
                        model_provider=model_provider,
                        controller=controller,
                        emit=emit,
                    )
                    retry_future = pool.submit(retry_worker.run)
                    controller.register_future(retry_future)
                    futures[retry_future] = retry_spec
                    attempts[retry_future] = attempts[future] + 1
                    pending.add(retry_future)
                    continue
                reports.append(report)
                storage.write_json(task_id, f"subagents/{category}.json", report)
                emit(
                    "subagent_completed",
                    f"{CATEGORY_LABELS[category]} completed",
                    {"category": category, "findings": len(report["evidence"])},
                )

    evidence = normalize_evidence(reports)
    storage.write_json(task_id, "artifacts/evidence.json", evidence)
    summary = render_summary(classified, evidence)
    storage.write_text(task_id, "artifacts/final-summary.md", summary)
    html_report = render_html_report(classified, evidence, plan)
    storage.write_text(task_id, "artifacts/report.html", html_report)
    emit(
        "artifacts_written",
        "Final report artifacts were written",
        {"artifacts": ["task-plan.md", "evidence.json", "final-summary.md", "report.html"]},
    )
    return {
        "document_count": len(classified),
        "bidder_count": len(bidder_docs),
        "evidence_count": len(evidence),
        "artifacts": ["report.html", "final-summary.md", "evidence.json", "task-plan.md"],
    }


class CancelledError(RuntimeError):
    pass


class NeedsInputError(RuntimeError):
    def __init__(self, message: str, payload: dict[str, Any]):
        super().__init__(message)
        self.payload = payload


def load_markdown_documents(paths: list[Path]) -> list[MarkdownDocument]:
    documents = []
    for path in sorted(paths):
        text = path.read_text(encoding="utf-8", errors="ignore")
        documents.append(
            MarkdownDocument(
                filename=path.name,
                role="unknown",
                bidder_name=None,
                text=text,
                lines=text.splitlines(),
            )
        )
    return documents


def classify_documents(documents: list[MarkdownDocument]) -> list[MarkdownDocument]:
    tender_index: int | None = None
    for index, doc in enumerate(documents):
        filename = doc.filename.lower()
        if any(marker in filename for marker in TENDER_FILENAME_MARKERS):
            tender_index = index
            break
        if has_tender_document_heading(doc):
            tender_index = index
            break

    bidder_counter = 0
    classified: list[MarkdownDocument] = []
    for index, doc in enumerate(documents):
        if index == tender_index:
            classified.append(MarkdownDocument(doc.filename, "tender", None, doc.text, doc.lines))
            continue
        bidder_counter += 1
        bidder_name = infer_bidder_name(doc, bidder_counter)
        classified.append(
            MarkdownDocument(doc.filename, "bidder", bidder_name, doc.text, doc.lines)
        )
    return classified


def has_tender_document_heading(doc: MarkdownDocument) -> bool:
    for line in doc.lines[:20]:
        if any(pattern.search(line) for pattern in TENDER_HEADING_PATTERNS):
            return True
    return False


def render_input_manifest(documents: list[MarkdownDocument]) -> list[dict[str, Any]]:
    return [
        {
            "filename": doc.filename,
            "role": doc.role,
            "bidder_name": doc.bidder_name,
            "line_count": len(doc.lines),
            "character_count": len(doc.text),
        }
        for doc in documents
    ]


def infer_bidder_name(doc: MarkdownDocument, fallback_index: int) -> str:
    patterns = [
        r"(?:投标人|供应商|公司名称| bidder)[:：]\s*([^\n#|]+)",
        r"^#\s*([^\n#]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, doc.text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            name = match.group(1).strip()
            if 1 <= len(name) <= 60:
                return name
    stem = Path(doc.filename).stem
    cleaned = re.sub(r"(?i)(bid|bidder|投标|响应|报价|document|文件|[_\-\s]+)", "", stem).strip()
    return cleaned or f"Bidder {fallback_index}"


def build_execution_plan(task_message: str, documents: list[MarkdownDocument]) -> dict[str, Any]:
    roles = [
        {"filename": doc.filename, "role": doc.role, "bidder_name": doc.bidder_name}
        for doc in documents
    ]
    return {
        "task_type": "bid_collusion_suspicion_analysis",
        "input_material_roles": roles,
        "user_request": task_message,
        "analysis_dimensions": [
            {"id": category, "label": CATEGORY_LABELS[category]} for category in BID_CATEGORIES
        ],
        "evidence_recording_format": {
            "required": ["severity", "category", "title", "description", "bidders", "locations"],
            "location_fields": ["file", "line", "heading", "snippet"],
            "page_number": "optional when present in Markdown/OCR text",
        },
        "sub_agent_staffing": [
            {
                "agent_id": f"subagent-{category}",
                "scope": CATEGORY_LABELS[category],
                "prompt": build_subagent_prompt(category, task_message),
                "tools": list(SUBAGENT_TOOL_NAMES),
                "input_roles": ["tender", "bidder"],
            }
            for category in BID_CATEGORIES
        ],
        "stopping_conditions": [
            "All category subagents complete or exhaust retry budget",
            "Evidence is normalized and grouped by bidder/category/severity",
            "Interactive HTML report and Markdown summary are written",
            "Cancellation token is observed if user stops the task",
        ],
        "auto_start": True,
    }


def render_plan_markdown(plan: dict[str, Any]) -> str:
    dimensions = "\n".join(
        f"- {item['label']} (`{item['id']}`)" for item in plan["analysis_dimensions"]
    )
    roles = "\n".join(
        f"- `{item['filename']}`: {item['role']}"
        + (f" ({item['bidder_name']})" if item.get("bidder_name") else "")
        for item in plan["input_material_roles"]
    )
    agents = "\n".join(
        f"- `{item['agent_id']}`: {item['scope']}" for item in plan["sub_agent_staffing"]
    )
    return (
        "# Execution Plan\n\n"
        f"Task type: `{plan['task_type']}`\n\n"
        "## Input Roles\n"
        f"{roles}\n\n"
        "## Analysis Dimensions\n"
        f"{dimensions}\n\n"
        "## Concurrent Sub-Agents\n"
        f"{agents}\n\n"
        "## Stopping Conditions\n"
        + "\n".join(f"- {item}" for item in plan["stopping_conditions"])
        + "\n"
    )


def build_subagent_specs(
    task_message: str, documents: list[MarkdownDocument]
) -> list[SubAgentSpec]:
    input_files = [doc.filename for doc in documents]
    return [
        SubAgentSpec(
            agent_id=f"subagent-{category}",
            category=category,
            label=CATEGORY_LABELS[category],
            prompt=build_subagent_prompt(category, task_message),
            tools=list(SUBAGENT_TOOL_NAMES),
            input_files=input_files,
        )
        for category in BID_CATEGORIES
    ]


def build_subagent_prompt(category: str, task_message: str) -> str:
    return (
        f"User task: {task_message}\n"
        f"Act as a bounded evidence sub-agent for: {CATEGORY_LABELS[category]}.\n"
        "Use scoped workspace tools to inspect uploaded Markdown files, record only traceable "
        "evidence, and return a structured sub-agent report for supervisor aggregation."
    )


class SubAgentWorker:
    def __init__(
        self,
        *,
        spec: SubAgentSpec,
        tender_docs: list[MarkdownDocument],
        bidder_docs: list[MarkdownDocument],
        tools: WorkspaceTools,
        model: str,
        model_provider: ModelProvider,
        controller: CancellationController,
        emit: Emit,
    ) -> None:
        self.spec = spec
        self.tender_docs = tender_docs
        self.bidder_docs = bidder_docs
        self.tools = tools
        self.model = model
        self.model_provider = model_provider
        self.controller = controller
        self.emit = emit
        self.tool_calls: list[dict[str, Any]] = []

    def run(self) -> dict[str, Any]:
        try:
            self._raise_if_cancelled()
            self.emit(
                "subagent_assigned",
                f"{self.spec.agent_id} received a bounded prompt",
                {
                    "agent_id": self.spec.agent_id,
                    "category": self.spec.category,
                    "prompt": self.spec.prompt,
                },
            )
            self._call_tool(
                "list_dir", {"relative_path": "uploads"}, lambda: self.tools.list_dir("uploads")
            )
            for doc in [*self.tender_docs, *self.bidder_docs]:
                self._raise_if_cancelled()
                self._call_tool(
                    "read_file",
                    {"relative_path": f"uploads/{doc.filename}"},
                    partial(self.tools.read_file, f"uploads/{doc.filename}"),
                )
            if self.spec.category in {
                "requirement_deviations",
                "shared_entities",
                "template_traces",
            }:
                self._call_tool(
                    "full_text_search",
                    {"query": self._search_probe(), "suffix": ".md"},
                    lambda: self.tools.full_text_search(self._search_probe(), ".md"),
                )
            if self.spec.category == "requirement_deviations":
                self._call_tool(
                    "tavily_search",
                    {
                        "query": "bid collusion red flags tender response deviation",
                        "max_results": 3,
                    },
                    lambda: self.tools.tavily_search(
                        "bid collusion red flags tender response deviation", 3
                    ),
                )
            reasoning = self._model_reasoning()
            evidence = self._inspect()
            self._raise_if_cancelled()
            return {
                "agent_id": self.spec.agent_id,
                "category": self.spec.category,
                "label": self.spec.label,
                "status": "complete",
                "prompt": self.spec.prompt,
                "model": self.model,
                "reasoning": reasoning,
                "tools": self.tool_calls,
                "evidence": evidence,
            }
        except RuntimeError as exc:
            if self.controller.is_cancelled():
                raise CancelledError() from exc
            raise

    def _inspect(self) -> list[dict[str, Any]]:
        if self.spec.category == "technical_text_similarity":
            return inspect_text_similarity(self.tender_docs, self.bidder_docs, self.controller)
        functions = {
            "quotation_similarity": inspect_quotation_similarity,
            "template_traces": inspect_template_traces,
            "shared_entities": inspect_shared_entities,
            "requirement_deviations": inspect_requirement_deviations,
            "metadata_clues": inspect_metadata_clues,
            "common_deviations": inspect_common_deviations,
        }
        return functions[self.spec.category](self.tender_docs, self.bidder_docs)

    def _model_reasoning(self) -> str:
        context = "\n".join(
            f"- {call['tool']} {call['args']}: {call['result_summary']}" for call in self.tool_calls
        )
        prompt = (
            f"{self.spec.prompt}\n\n"
            "Tool context summaries:\n"
            f"{context}\n\n"
            "Reason about what evidence this category should accept or reject. "
            "Return concise rationale; deterministic evidence extraction will normalize citations."
        )
        self.emit(
            "model_call",
            f"{self.spec.agent_id} requested model reasoning",
            {"agent_id": self.spec.agent_id, "model": self.model, "category": self.spec.category},
        )
        try:
            reasoning = self.model_provider.reason(prompt, self.model, self.controller)
        except CancelledError:
            raise
        except Exception as exc:
            if self.controller.is_cancelled():
                raise CancelledError() from exc
            fallback = (
                "MODEL_FALLBACK: model reasoning failed "
                f"({type(exc).__name__}: {exc}); deterministic evidence extraction continued."
            )
            self.emit(
                "model_warning",
                f"{self.spec.agent_id} model reasoning failed; deterministic analysis continued",
                {
                    "agent_id": self.spec.agent_id,
                    "model": self.model,
                    "category": self.spec.category,
                    "error": str(exc),
                },
            )
            return fallback
        self.emit(
            "model_result",
            f"{self.spec.agent_id} completed model reasoning",
            {
                "agent_id": self.spec.agent_id,
                "model": self.model,
                "summary": reasoning[:240],
            },
        )
        return reasoning

    def _call_tool(self, name: str, args: dict[str, Any], call: Callable[[], Any]) -> Any:
        self._raise_if_cancelled()
        self.emit(
            "tool_call",
            f"{self.spec.agent_id} called {name}",
            {"agent_id": self.spec.agent_id, "tool": name, "args": args},
        )
        result = call()
        summary = summarize_tool_result(result)
        self.tool_calls.append({"tool": name, "args": args, "result_summary": summary})
        self.emit(
            "tool_result",
            f"{self.spec.agent_id} completed {name}",
            {"agent_id": self.spec.agent_id, "tool": name, "summary": summary},
        )
        self._raise_if_cancelled()
        return result

    def _search_probe(self) -> str:
        probes = {
            "requirement_deviations": "资质",
            "shared_entities": "联系人",
            "template_traces": "目录",
        }
        return probes.get(self.spec.category, "投标")

    def _raise_if_cancelled(self) -> None:
        if self.controller.is_cancelled():
            raise CancelledError()


def summarize_tool_result(result: Any) -> dict[str, Any]:
    if isinstance(result, list):
        return {"type": "list", "count": len(result), "preview": result[:3]}
    if isinstance(result, str):
        return {"type": "text", "chars": len(result), "preview": result[:160]}
    if isinstance(result, dict):
        return {"type": "object", "keys": sorted(result.keys())[:8]}
    return {"type": type(result).__name__}


def inspect_quotation_similarity(
    tender_docs: list[MarkdownDocument], bidder_docs: list[MarkdownDocument]
) -> list[dict[str, Any]]:
    del tender_docs
    evidence: list[dict[str, Any]] = []
    value_sets = {
        doc.bidder_name or doc.filename: extract_quotation_values(doc.text) for doc in bidder_docs
    }
    for left, right in itertools.combinations(bidder_docs, 2):
        left_name = left.bidder_name or left.filename
        right_name = right.bidder_name or right.filename
        overlap = sorted(value_sets[left_name] & value_sets[right_name])
        if len(overlap) >= 2:
            evidence.append(
                make_evidence(
                    "quotation_similarity",
                    "medium" if len(overlap) < 5 else "high",
                    [left_name, right_name],
                    "Repeated quotation values",
                    f"{left_name} and {right_name} share {len(overlap)} numeric quotation values.",
                    find_quotation_locations([left, right], overlap[:3]),
                    {"values": overlap[:12]},
                )
            )
    return evidence


def inspect_text_similarity(
    tender_docs: list[MarkdownDocument],
    bidder_docs: list[MarkdownDocument],
    controller: CancellationController | None = None,
) -> list[dict[str, Any]]:
    del tender_docs
    evidence: list[dict[str, Any]] = []
    for left, right in itertools.combinations(bidder_docs, 2):
        if controller is not None and controller.is_cancelled():
            raise CancelledError()
        pairs = similar_paragraph_pairs(left, right, controller)
        if pairs:
            left_name = left.bidder_name or left.filename
            right_name = right.bidder_name or right.filename
            strongest = pairs[0]
            evidence.append(
                make_evidence(
                    "technical_text_similarity",
                    "high" if strongest["score"] >= 0.92 else "medium",
                    [left_name, right_name],
                    "Highly similar technical text",
                    f"{left_name} and {right_name} contain similar proposal paragraphs.",
                    [
                        location_from_line(left, strongest["left_line"], strongest["left_text"]),
                        location_from_line(right, strongest["right_line"], strongest["right_text"]),
                    ],
                    {"score": strongest["score"]},
                )
            )
    return evidence


def inspect_template_traces(
    tender_docs: list[MarkdownDocument], bidder_docs: list[MarkdownDocument]
) -> list[dict[str, Any]]:
    del tender_docs
    markers = ["错别字", "目录", "格式", "模板", "TODO", "占位", "样表", "（此处填写）"]
    evidence: list[dict[str, Any]] = []
    for marker in markers:
        docs = [doc for doc in bidder_docs if marker.lower() in doc.text.lower()]
        if len(docs) >= 2:
            evidence.append(
                make_evidence(
                    "template_traces",
                    "medium",
                    [doc.bidder_name or doc.filename for doc in docs],
                    f"Shared template marker: {marker}",
                    "Multiple bidder documents contain the same formatting/template clue.",
                    find_locations(docs, [marker]),
                    {"marker": marker},
                )
            )
    return evidence


def inspect_shared_entities(
    tender_docs: list[MarkdownDocument], bidder_docs: list[MarkdownDocument]
) -> list[dict[str, Any]]:
    del tender_docs
    entity_index: dict[str, list[MarkdownDocument]] = {}
    for doc in bidder_docs:
        for entity in extract_entities(doc.text):
            entity_index.setdefault(entity, []).append(doc)
    evidence = []
    for entity, docs in sorted(entity_index.items()):
        unique_docs = dedupe_docs(docs)
        if len(unique_docs) >= 2:
            evidence.append(
                make_evidence(
                    "shared_entities",
                    "medium",
                    [doc.bidder_name or doc.filename for doc in unique_docs],
                    f"Repeated entity: {entity}",
                    "The same person, company, contact, or place appears in multiple bidder documents.",
                    find_locations(unique_docs, [entity]),
                    {"entity": entity},
                )
            )
            if len(evidence) >= 8:
                break
    return evidence


def inspect_requirement_deviations(
    tender_docs: list[MarkdownDocument], bidder_docs: list[MarkdownDocument]
) -> list[dict[str, Any]]:
    requirements = extract_requirements(tender_docs)
    if not requirements:
        return []
    evidence: list[dict[str, Any]] = []
    for requirement in requirements[:8]:
        missing_docs = [
            doc for doc in bidder_docs if requirement["keyword"].lower() not in doc.text.lower()
        ]
        if len(missing_docs) >= 2:
            evidence.append(
                make_evidence(
                    "requirement_deviations",
                    "low" if len(missing_docs) < len(bidder_docs) else "medium",
                    [doc.bidder_name or doc.filename for doc in missing_docs],
                    f"Common missing response: {requirement['keyword']}",
                    "Multiple bidder documents do not explicitly respond to a tender requirement keyword.",
                    [requirement["location"]],
                    {"requirement": requirement["text"]},
                )
            )
    return evidence


def inspect_metadata_clues(
    tender_docs: list[MarkdownDocument], bidder_docs: list[MarkdownDocument]
) -> list[dict[str, Any]]:
    del tender_docs
    metadata_patterns = [
        r"(?:作者|author)[:：]\s*([^\n]+)",
        r"(?:创建时间|created)[:：]\s*([^\n]+)",
    ]
    index: dict[str, list[MarkdownDocument]] = {}
    for doc in bidder_docs:
        for pattern in metadata_patterns:
            for match in re.finditer(pattern, doc.text, flags=re.IGNORECASE):
                value = match.group(1).strip()
                if value:
                    index.setdefault(value, []).append(doc)
    evidence = []
    for value, docs in index.items():
        unique_docs = dedupe_docs(docs)
        if len(unique_docs) >= 2:
            evidence.append(
                make_evidence(
                    "metadata_clues",
                    "medium",
                    [doc.bidder_name or doc.filename for doc in unique_docs],
                    f"Repeated metadata value: {value}",
                    "The same author/timestamp metadata appears across bidder documents.",
                    find_locations(unique_docs, [value]),
                    {"metadata_value": value},
                )
            )
    return evidence


def inspect_common_deviations(
    tender_docs: list[MarkdownDocument], bidder_docs: list[MarkdownDocument]
) -> list[dict[str, Any]]:
    del tender_docs
    markers = ["未响应", "偏离", "不满足", "例外", "无法提供", "待确认"]
    evidence = []
    for marker in markers:
        docs = [doc for doc in bidder_docs if marker in doc.text]
        if len(docs) >= 2:
            evidence.append(
                make_evidence(
                    "common_deviations",
                    "medium",
                    [doc.bidder_name or doc.filename for doc in docs],
                    f"Repeated deviation marker: {marker}",
                    "Multiple bidder documents contain the same deviation/exception wording.",
                    find_locations(docs, [marker]),
                    {"marker": marker},
                )
            )
    return evidence


def extract_quotation_values(text: str) -> set[str]:
    values = set()
    for line in text.splitlines():
        if not PRICE_CONTEXT_PATTERN.search(line):
            continue
        for match in re.finditer(r"(?<!\w)(?:\d{2,}(?:,\d{3})*|\d+\.\d+)\s*(?:元|万元|%)?", line):
            raw_value = match.group(0).strip()
            if not raw_value:
                continue
            if is_likely_non_price_number(line, raw_value):
                continue
            values.add(normalize_quotation_value(raw_value))
    return values


def normalize_quotation_value(value: str) -> str:
    return re.sub(r"\s+", "", value.replace(",", ""))


def is_likely_non_price_number(line: str, value: str) -> bool:
    normalized = normalize_quotation_value(value)
    has_price_unit = normalized.endswith(("元", "万元", "%"))
    if has_price_unit:
        return False
    if NON_PRICE_CONTEXT_PATTERN.search(line):
        return True
    digits = re.sub(r"\D", "", normalized)
    return bool(re.fullmatch(r"(?:19|20)\d{2}", digits))


def find_quotation_locations(
    docs: list[MarkdownDocument], canonical_values: list[str]
) -> list[dict[str, Any]]:
    locations = []
    wanted = set(canonical_values)
    for doc in docs:
        for line_number, line in enumerate(doc.lines, start=1):
            if extract_quotation_values(line) & wanted:
                locations.append(location_from_line(doc, line_number, line))
                break
    return locations


def extract_entities(text: str) -> set[str]:
    entities = set()
    patterns = [
        r"[\u4e00-\u9fffA-Za-z0-9]{2,40}(?:有限公司|集团|公司|研究院|中心|项目部)",
        r"(?:联系人|项目经理|法定代表人|授权代表)[:：]\s*([^\n，,；;]{2,30})",
        r"(?:电话|手机|联系方式)[:：]\s*([0-9\- ]{7,20})",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            value = match.group(1).strip() if match.lastindex else match.group(0).strip()
            if value and len(value) <= 40:
                entities.add(value)
    return entities


def extract_requirements(tender_docs: list[MarkdownDocument]) -> list[dict[str, Any]]:
    requirements: list[dict[str, Any]] = []
    keyword_pattern = re.compile(r"(必须|须|应|不得|要求|评分|资质|工期|质量|人员|设备)")
    for doc in tender_docs:
        for index, line in enumerate(doc.lines, start=1):
            stripped = line.strip()
            if 8 <= len(stripped) <= 180 and keyword_pattern.search(stripped):
                keyword = pick_requirement_keyword(stripped)
                requirements.append(
                    {
                        "keyword": keyword,
                        "text": stripped,
                        "location": location_from_line(doc, index, stripped),
                    }
                )
    return requirements


def pick_requirement_keyword(line: str) -> str:
    for token in ["资质", "工期", "质量", "人员", "设备", "报价", "响应", "业绩", "方案"]:
        if token in line:
            return token
    words = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,}", line)
    return words[0] if words else line[:12]


def similar_paragraph_pairs(
    left: MarkdownDocument,
    right: MarkdownDocument,
    controller: CancellationController | None = None,
) -> list[dict[str, Any]]:
    left_paragraphs = extract_paragraphs(left)
    right_paragraphs = extract_paragraphs(right)
    pairs: list[dict[str, Any]] = []
    comparisons = 0
    for left_line, left_text in left_paragraphs:
        if controller is not None and controller.is_cancelled():
            raise CancelledError()
        for right_line, right_text in right_paragraphs:
            comparisons += 1
            if comparisons > MAX_SIMILARITY_COMPARISONS_PER_PAIR:
                return sorted(pairs, key=lambda item: item["score"], reverse=True)[:4]
            if comparisons % 500 == 0 and controller is not None and controller.is_cancelled():
                raise CancelledError()
            score = SequenceMatcher(
                None, normalize_text(left_text), normalize_text(right_text)
            ).ratio()
            if score >= 0.78:
                pairs.append(
                    {
                        "score": round(score, 3),
                        "left_line": left_line,
                        "left_text": left_text,
                        "right_line": right_line,
                        "right_text": right_text,
                    }
                )
    return sorted(pairs, key=lambda item: item["score"], reverse=True)[:4]


def extract_paragraphs(doc: MarkdownDocument) -> list[tuple[int, str]]:
    paragraphs = []
    for index, line in enumerate(doc.lines, start=1):
        stripped = line.strip()
        if len(stripped) >= 24 and not stripped.startswith("|"):
            paragraphs.append((index, stripped[:500]))
            if len(paragraphs) >= MAX_SIMILARITY_PARAGRAPHS_PER_DOCUMENT:
                break
    return paragraphs


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", text.lower())


def find_locations(docs: list[MarkdownDocument], terms: list[str]) -> list[dict[str, Any]]:
    locations = []
    folded_terms = [term.casefold() for term in terms if term]
    for doc in docs:
        for line_number, line in enumerate(doc.lines, start=1):
            folded_line = line.casefold()
            if any(term in folded_line for term in folded_terms):
                locations.append(location_from_line(doc, line_number, line))
                break
    return locations


def location_from_line(doc: MarkdownDocument, line_number: int, line: str) -> dict[str, Any]:
    return {
        "file": doc.filename,
        "line": line_number,
        "heading": nearest_heading(doc.lines, line_number),
        "snippet": line.strip()[:260],
    }


def nearest_heading(lines: list[str], line_number: int) -> str | None:
    for index in range(line_number - 1, -1, -1):
        line = lines[index].strip()
        if line.startswith("#"):
            return line.lstrip("#").strip()
    return None


def make_evidence(
    category: str,
    severity: str,
    bidders: list[str],
    title: str,
    description: str,
    locations: list[dict[str, Any]],
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "category": category,
        "category_label": CATEGORY_LABELS[category],
        "severity": severity,
        "bidders": bidders,
        "title": title,
        "description": description,
        "locations": locations,
        "details": details or {},
    }


def normalize_evidence(reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    counter = 1
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    for report in sorted(reports, key=lambda item: item["category"]):
        for item in report["evidence"]:
            normalized = dict(item)
            normalized["id"] = f"E-{counter:03d}"
            counter += 1
            evidence.append(normalized)
    return sorted(evidence, key=lambda item: (severity_rank.get(item["severity"], 9), item["id"]))


def dedupe_docs(docs: list[MarkdownDocument]) -> list[MarkdownDocument]:
    by_name = {doc.filename: doc for doc in docs}
    return list(by_name.values())


def render_summary(documents: list[MarkdownDocument], evidence: list[dict[str, Any]]) -> str:
    bidder_names = [doc.bidder_name or doc.filename for doc in documents if doc.role == "bidder"]
    counts = {
        severity: sum(1 for item in evidence if item["severity"] == severity)
        for severity in ["high", "medium", "low"]
    }
    lines = [
        "# Final Summary",
        "",
        f"- Documents reviewed: {len(documents)}",
        f"- Bidders compared: {', '.join(bidder_names) if bidder_names else 'none'}",
        f"- Evidence: {counts['high']} high, {counts['medium']} medium, {counts['low']} low",
        "",
        "## Evidence Highlights",
    ]
    for item in evidence[:12]:
        bidders = ", ".join(item["bidders"])
        lines.append(f"- **{item['severity'].upper()}** `{item['id']}` {item['title']} ({bidders})")
    if not evidence:
        lines.append(
            "- No material suspicion evidence was detected by the v1 deterministic checks."
        )
    return "\n".join(lines) + "\n"


def render_html_report(
    documents: list[MarkdownDocument], evidence: list[dict[str, Any]], plan: dict[str, Any]
) -> str:
    bidder_names = [doc.bidder_name or doc.filename for doc in documents if doc.role == "bidder"]
    categories = sorted({item["category"] for item in evidence} | set(BID_CATEGORIES))
    table_rows = render_comparison_rows(bidder_names, categories, evidence)
    evidence_cards = "\n".join(render_evidence_card(item) for item in evidence) or (
        '<article class="evidence-card" data-severity="low" data-category="none" data-bidders="">'
        "<h3>No suspicious evidence detected</h3><p>The v1 checks did not produce report-worthy findings.</p></article>"
    )
    category_options = "\n".join(
        f'<option value="{escape(category)}">{escape(CATEGORY_LABELS.get(category, category))}</option>'
        for category in categories
    )
    bidder_options = "\n".join(
        f'<option value="{escape(name)}">{escape(name)}</option>' for name in bidder_names
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Bid Suspicion Analysis Report</title>
  <style>
    body {{ margin: 0; font-family: Arial, sans-serif; color: #1f2937; background: #f6f7f9; }}
    header {{ padding: 28px 36px 18px; background: #ffffff; border-bottom: 1px solid #d8dee8; }}
    h1 {{ margin: 0 0 8px; font-size: 26px; }}
    main {{ padding: 24px 36px 40px; }}
    .controls {{ display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin-bottom: 18px; }}
    .controls label {{ display: inline-flex; gap: 6px; align-items: center; background: #fff; border: 1px solid #d8dee8; padding: 8px 10px; border-radius: 6px; }}
    select {{ padding: 8px 10px; border: 1px solid #d8dee8; border-radius: 6px; background: #fff; }}
    table {{ width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #d8dee8; margin-bottom: 22px; }}
    th, td {{ border-bottom: 1px solid #e5e9f0; padding: 10px; text-align: left; vertical-align: top; }}
    th {{ background: #eef2f7; font-size: 13px; }}
    .evidence-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 12px; }}
    .evidence-card {{ background: #fff; border: 1px solid #d8dee8; border-left: 5px solid #9aa4b2; border-radius: 6px; padding: 14px; }}
    .evidence-card.high {{ border-left-color: #b42318; }}
    .evidence-card.medium {{ border-left-color: #c77700; }}
    .evidence-card.low {{ border-left-color: #276749; }}
    .meta {{ color: #5b6675; font-size: 13px; }}
    .location {{ margin-top: 8px; padding: 8px; background: #f6f7f9; border-radius: 4px; font-size: 13px; }}
    .hidden {{ display: none; }}
  </style>
</head>
<body>
  <header>
    <h1>Bid Suspicion Analysis Report</h1>
    <p class="meta">Task type: {escape(plan["task_type"])}. This report marks weakly supported items as suspicion evidence, not final legal conclusions.</p>
  </header>
  <main>
    <section class="controls" aria-label="Report filters">
      <label><input type="checkbox" data-severity="high" checked /> High</label>
      <label><input type="checkbox" data-severity="medium" checked /> Medium</label>
      <label><input type="checkbox" data-severity="low" checked /> Low</label>
      <select id="bidderFilter"><option value="">All bidders</option>{bidder_options}</select>
      <select id="categoryFilter"><option value="">All categories</option>{category_options}</select>
    </section>
    <section>
      <h2>Three-Bidder Comparison View</h2>
      <table>
        <thead><tr><th>Review item</th>{"".join(f"<th>{escape(name)}</th>" for name in bidder_names)}</tr></thead>
        <tbody>{table_rows}</tbody>
      </table>
    </section>
    <section>
      <h2>Evidence</h2>
      <div class="evidence-grid">{evidence_cards}</div>
    </section>
  </main>
  <script>
    function applyFilters() {{
      const severities = new Set([...document.querySelectorAll('[data-severity][type="checkbox"]:checked')].map(el => el.dataset.severity));
      const bidder = document.getElementById('bidderFilter').value;
      const category = document.getElementById('categoryFilter').value;
      document.querySelectorAll('.evidence-card, tr[data-category]').forEach(el => {{
        const severityOk = !el.dataset.severity || severities.has(el.dataset.severity);
        const bidderOk = !bidder || (el.dataset.bidders || '').includes(bidder);
        const categoryOk = !category || el.dataset.category === category;
        el.classList.toggle('hidden', !(severityOk && bidderOk && categoryOk));
      }});
    }}
    document.querySelectorAll('input, select').forEach(el => el.addEventListener('change', applyFilters));
    applyFilters();
  </script>
</body>
</html>
"""


def render_comparison_rows(
    bidder_names: list[str], categories: list[str], evidence: list[dict[str, Any]]
) -> str:
    rows = []
    for category in categories:
        category_evidence = [item for item in evidence if item["category"] == category]
        severity = max_severity(category_evidence)
        cells = []
        for bidder in bidder_names:
            bidder_items = [item for item in category_evidence if bidder in item["bidders"]]
            if bidder_items:
                cells.append(
                    "<br>".join(
                        f"{escape(item['severity'].upper())}: {escape(item['title'])}"
                        for item in bidder_items[:3]
                    )
                )
            else:
                cells.append("No evidence recorded")
        bidders = ",".join(
            sorted({bidder for item in category_evidence for bidder in item["bidders"]})
        )
        rows.append(
            f'<tr data-category="{escape(category)}" data-severity="{severity}" data-bidders="{escape(bidders)}">'
            f"<td>{escape(CATEGORY_LABELS.get(category, category))}</td>"
            + "".join(f"<td>{cell}</td>" for cell in cells)
            + "</tr>"
        )
    return "\n".join(rows)


def max_severity(items: list[dict[str, Any]]) -> str:
    if any(item["severity"] == "high" for item in items):
        return "high"
    if any(item["severity"] == "medium" for item in items):
        return "medium"
    return "low"


def render_evidence_card(item: dict[str, Any]) -> str:
    locations = "".join(
        '<div class="location">'
        f"<strong>{escape(location['file'])}:{location['line']}</strong>"
        + (f" - {escape(location['heading'])}" if location.get("heading") else "")
        + f"<br>{escape(location['snippet'])}</div>"
        for location in item["locations"]
    )
    bidders = ", ".join(item["bidders"])
    return (
        f'<article class="evidence-card {escape(item["severity"])}" '
        f'data-severity="{escape(item["severity"])}" '
        f'data-category="{escape(item["category"])}" '
        f'data-bidders="{escape(bidders)}">'
        f"<h3>{escape(item['id'])}: {escape(item['title'])}</h3>"
        f"<p>{escape(item['description'])}</p>"
        f'<p class="meta">Severity: {escape(item["severity"])} | Bidders: {escape(bidders)} | Category: {escape(item["category_label"])}</p>'
        f"{locations}</article>"
    )
