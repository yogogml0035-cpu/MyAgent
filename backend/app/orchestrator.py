from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from .agent_activity import activity_payload_from_file_audit
from .agent_profiles import (
    DEFAULT_FILE_AGENT_PROFILE,
    AgentProfile,
    agent_profile_manifest,
)
from .analysis import (
    bidder_pairs,
    classify_documents,
    load_analysis_documents,
    validate_bid_evidence_records,
)
from .deep_agent_runtime import (
    DEEP_AGENT_NO_FINAL_MESSAGE,
    DeepAgentRunRequest,
    DeepAgentRunResult,
    DeepAgentRuntime,
)
from .permissions import PermissionPolicy
from .reasoning_trace import ReasoningConfidence, ReasoningPhase, build_safe_exception_payload
from .runtime import CancellationController
from .storage import TaskStorage, safe_filename
from .tools import AuditedWorkspaceTools, safe_audit_path

CANONICAL_BID_OUTPUT_NAMES = {"report.html", "final-summary.md", "evidence.json", "task-plan.md"}
BID_WORKFLOW_MARKERS = ("串标", "围标", "投标", "招标", "bid", "tender", "collusion")


class DeepAgentOrchestrator:
    """Thin task-scoped adapter that keeps DeepAgent away from raw filesystem paths."""

    def __init__(
        self,
        *,
        storage: TaskStorage,
        task_id: str,
        run_id: str,
        model: str,
        controller: CancellationController,
        uploads: list[Path] | None = None,
        agent_factory: Callable[..., Any] | None = None,
        agent_profile: AgentProfile = DEFAULT_FILE_AGENT_PROFILE,
        read_chunk_chars: int = 1024 * 1024,
        write_chunk_chars: int = 1024 * 1024,
    ) -> None:
        self.storage = storage
        self.task_id = task_id
        self.run_id = run_id
        self.model = model
        self.controller = controller
        self.agent_profile = agent_profile
        self.upload_names = [upload.name for upload in uploads or []]
        self.workspace_root = (
            storage.task_dir(task_id) / "agent_workspace" / "runs" / run_id
        ).resolve()
        self._prepare_workspace(uploads or [])
        self.file_tools = AuditedWorkspaceTools(
            self.workspace_root,
            PermissionPolicy(self.workspace_root),
            controller,
            self._append_audit,
            read_chunk_chars=read_chunk_chars,
            write_chunk_chars=write_chunk_chars,
            writable_roots=("records", "outputs"),
        )
        self.runtime = DeepAgentRuntime(
            self.file_tools,
            agent_factory=agent_factory,
            activity_sink=self._append_activity,
        )

    def run(self, message: str) -> DeepAgentRunResult:
        self._append_reasoning_trace(
            agent_id="deep-agent",
            phase="plan",
            summary=(
                "DeepAgent 将在本轮隔离工作区内执行任务；uploads/ 中的上传快照"
                "只是可用上下文，是否读取由模型按任务需要自主决定，并只把可交付文件写入 outputs/。"
            ),
            confidence="high",
            evidence_refs=[f"uploads/{name}" for name in self.upload_names],
        )
        result = self.runtime.run(
            DeepAgentRunRequest(
                task_id=self.task_id,
                run_id=self.run_id,
                message=message,
                model=self.model,
                agent_profile=self.agent_profile,
            ),
            controller=self.controller,
        )
        promoted = self.promote_outputs(message)
        metadata = dict(result.metadata)
        metadata["workspace_root"] = "agent_workspace/runs/" + self.run_id
        metadata["promoted_artifacts"] = promoted
        metadata["agent_profile"] = agent_profile_manifest(self.agent_profile)
        output_text = result.output_text
        if metadata.get("result_type") == "stream_no_assistant_final" or (
            output_text == DEEP_AGENT_NO_FINAL_MESSAGE
        ):
            output_text = self._synthesize_missing_final_answer(promoted)
            metadata["warning_code"] = "missing_deep_agent_final"
        result = DeepAgentRunResult(
            status=result.status,
            output_text=output_text,
            metadata=metadata,
        )
        self._append_reasoning_trace(
            agent_id="deep-agent",
            phase="final_summary",
            summary=(
                f"DeepAgent 本轮完成，已提升 {len(promoted)} 个输出产物；"
                "日志只记录虚拟路径和审计元数据。"
            ),
            confidence="medium" if promoted else "low",
            evidence_refs=promoted,
        )
        return result

    def _append_audit(self, record: dict[str, Any]) -> None:
        audit_event = self.storage.append_file_tool_audit(self.task_id, self.run_id, record)
        try:
            self._append_activity(
                activity_payload_from_file_audit(
                    audit_event.payload,
                    related_event_id=audit_event.id,
                )
            )
        except Exception as exc:
            self.storage.append_event(
                self.task_id,
                "deep_agent_activity_warning",
                "DeepAgent 执行活动记录失败，已继续执行。",
                build_safe_exception_payload(exc),
                run_id=self.run_id,
                level="warning",
            )
        try:
            self._append_reasoning_trace(
                agent_id="deep-agent",
                phase="observe",
                summary=self._audit_observation_summary(audit_event.payload),
                confidence="medium",
                evidence_refs=[
                    safe_audit_path(str(audit_event.payload.get("virtual_path") or ""))
                    or ""
                ],
                source_event_id=audit_event.id,
            )
        except Exception as exc:
            self.storage.append_event(
                self.task_id,
                "reasoning_warning",
                "DeepAgent 思考摘要记录失败，已继续执行。",
                {"agent_id": "deep-agent", **build_safe_exception_payload(exc)},
                run_id=self.run_id,
                level="warning",
            )

    def _append_activity(self, payload: dict[str, Any]) -> None:
        level = self._activity_level(payload)
        message = str(payload.get("title") or "DeepAgent 执行活动已更新。")
        self.storage.append_event(
            self.task_id,
            "deep_agent_activity",
            message,
            payload,
            run_id=self.run_id,
            level=level,
        )

    @staticmethod
    def _activity_level(payload: dict[str, Any]) -> Literal["info", "success", "warning", "error"]:
        status = str(payload.get("status") or "")
        if status == "failed":
            return "error"
        if status == "skipped":
            return "warning"
        if status == "completed":
            return "success"
        return "info"

    def _append_reasoning_trace(
        self,
        *,
        agent_id: str,
        phase: ReasoningPhase,
        summary: str,
        confidence: ReasoningConfidence | None = None,
        evidence_refs: list[str] | None = None,
        source_event_id: str | None = None,
    ) -> None:
        self.storage.append_reasoning_trace(
            self.task_id,
            self.run_id,
            agent_id=agent_id,
            phase=phase,
            summary=summary,
            confidence=confidence,
            evidence_refs=evidence_refs or [],
            source_event_id=source_event_id,
        )

    @staticmethod
    def _audit_observation_summary(payload: dict[str, Any]) -> str:
        op_labels = {
            "list": "列出目录",
            "read": "读取文件",
            "write": "写入文件",
            "glob": "匹配文件名",
            "grep": "检索文件内容",
        }
        status_labels = {
            "success": "成功",
            "denied": "被拒绝",
            "cancelled": "已取消",
            "failed": "失败",
        }
        op = str(payload.get("op") or payload.get("operation") or "操作")
        status = str(payload.get("status") or "unknown")
        virtual_path = (
            safe_audit_path(str(payload.get("virtual_path") or payload.get("relative_path") or ""))
            or ""
        )
        source = str(payload.get("source") or "workspace")
        source_label = {
            "upload_snapshot": "上传快照",
            "record": "过程记录",
            "output": "输出区",
        }.get(source, "工作区")
        return (
            f"{op_labels.get(op, op)}{status_labels.get(status, status)}："
            f"{virtual_path or '工作区'}（{source_label}）。"
        )

    def _prepare_workspace(self, uploads: list[Path]) -> None:
        self.controller.raise_if_cancelled()
        for child in ("uploads", "records", "outputs"):
            (self.workspace_root / child).mkdir(parents=True, exist_ok=True)
        for upload in uploads:
            self.controller.raise_if_cancelled()
            destination = (self.workspace_root / "uploads" / upload.name).resolve()
            if self.workspace_root not in destination.parents:
                raise PermissionError("上传快照路径超出 DeepAgent 工作区")
            shutil.copy2(upload, destination)

    def promote_outputs(self, message: str = "") -> list[str]:
        output_root = self.workspace_root / "outputs"
        if not output_root.exists():
            return []
        output_paths = sorted(path for path in output_root.iterdir() if path.is_file())
        canonical_bid_outputs_ready = (
            self._canonical_bid_outputs_ready(output_paths)
            if is_bid_workflow_message(message)
            else False
        )
        promoted: list[str] = []
        used_names: set[str] = set()
        for path in output_paths:
            self.controller.raise_if_cancelled()
            artifact_name = self._promoted_artifact_name(
                path.name,
                used_names,
                canonical_bid_workflow=canonical_bid_outputs_ready,
            )
            text = path.read_text(encoding="utf-8", errors="ignore")
            self.storage.write_run_text(
                self.task_id,
                self.run_id,
                artifact_name,
                text,
            )
            self.storage.record_run_artifact(self.task_id, self.run_id, artifact_name)
            promoted.append(artifact_name)
        return promoted

    def _canonical_bid_outputs_ready(self, output_paths: list[Path]) -> bool:
        evidence_path = next((path for path in output_paths if path.name == "evidence.json"), None)
        if evidence_path is None:
            return False
        validate_canonical_bid_evidence_text(
            evidence_path.read_text(encoding="utf-8", errors="ignore"),
            required_pairs=self._required_bidder_pairs(),
        )
        return True

    def _required_bidder_pairs(self) -> list[list[str]]:
        upload_root = self.workspace_root / "uploads"
        if not upload_root.exists():
            return []
        upload_paths = sorted(path for path in upload_root.iterdir() if path.is_file())
        if len(upload_paths) < 2:
            return []
        documents = classify_documents(load_analysis_documents(upload_paths))
        bidder_names = [
            doc.bidder_name or doc.filename for doc in documents if doc.role == "bidder"
        ]
        if len(bidder_names) < 2:
            return []
        return bidder_pairs(bidder_names)

    @staticmethod
    def _promoted_artifact_name(
        source_name: str,
        used_names: set[str],
        *,
        canonical_bid_workflow: bool = False,
    ) -> str:
        if (
            canonical_bid_workflow
            and source_name in CANONICAL_BID_OUTPUT_NAMES
            and source_name not in used_names
        ):
            used_names.add(source_name)
            return source_name
        candidate = safe_filename(f"deep-agent-{source_name}")
        if candidate not in used_names:
            used_names.add(candidate)
            return candidate

        counter = 2
        while True:
            candidate = safe_filename(f"deep-agent-{counter}-{source_name}")
            if candidate not in used_names:
                used_names.add(candidate)
                return candidate
            counter += 1

    def _synthesize_missing_final_answer(self, promoted: list[str]) -> str:
        final_summary = self.storage.run_artifact_dir(self.task_id, self.run_id) / "final-summary.md"
        if final_summary.exists():
            text = final_summary.read_text(encoding="utf-8", errors="ignore").strip()
            if text:
                return text[:4000]
        if promoted:
            names = "、".join(f"`{name}`" for name in promoted[:8])
            return (
                "DeepAgent 未生成单独的最终回答；我已根据本轮安全执行结果保留可交付产物："
                f"{names}。请打开结果卡片查看。"
            )
        return "DeepAgent 未生成最终回答；本轮仅保留安全执行日志，没有生成可交付产物。"


def is_bid_workflow_message(message: str) -> bool:
    folded = message.casefold()
    return any(marker in folded for marker in BID_WORKFLOW_MARKERS)


def validate_canonical_bid_evidence_text(
    text: str,
    *,
    required_pairs: list[list[str]] | None = None,
) -> None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("DeepAgent 输出的 evidence.json 不是合法 JSON") from exc
    validate_bid_evidence_records(data, required_pairs=required_pairs)
