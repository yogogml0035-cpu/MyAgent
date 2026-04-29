from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from .intent import IntentDecision, is_bid_analysis_request
from .settings import MODEL_REGISTRY

AgentStrategy = Literal["single_agent", "multi_agent"]
ModelOverridePolicy = Literal["inherit_only", "allowlisted"]
ToolRegistry = Mapping[str, Callable[..., Any]]

DEFAULT_AGENT_PROFILE_ID = "default_file_agent"
BID_MULTI_AGENT_PROFILE_ID = "bid_multi_agent"
FILE_TOOL_ALIASES = ("list_dir", "read_file", "write_file")
SAFE_TOOL_ALIASES = set(FILE_TOOL_ALIASES)
SAFE_MODEL_IDS = {str(item["id"]) for item in MODEL_REGISTRY}
SAFE_PROFILE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")


class AgentProfileValidationError(ValueError):
    pass


@dataclass(frozen=True)
class SubAgentSpec:
    name: str
    description: str
    system_prompt: str
    tool_aliases: tuple[str, ...] = FILE_TOOL_ALIASES
    model: str | None = None


@dataclass(frozen=True)
class AgentProfile:
    id: str
    label: str
    strategy: AgentStrategy
    reason_code: str
    system_prompt_fragment: str
    subagents: tuple[SubAgentSpec, ...]
    allowed_tool_aliases: tuple[str, ...] = ("list_dir", "read_file", "write_file")
    model_override_policy: ModelOverridePolicy = "inherit_only"
    expected_outputs: tuple[str, ...] = ()
    observability_labels: dict[str, str] = field(default_factory=dict)
    compiled_factory: None = None

    @property
    def planned_subagents(self) -> list[str]:
        return [spec.name for spec in self.subagents]


DEFAULT_FILE_AGENT_PROFILE = AgentProfile(
    id=DEFAULT_AGENT_PROFILE_ID,
    label="默认文件任务 Agent",
    strategy="single_agent",
    reason_code="file_aware_single_agent",
    system_prompt_fragment=(
        "默认文件任务由主 Agent 判断是否读取 uploads/，只有明确需要文件依据时才读取上传快照。"
    ),
    subagents=(
        SubAgentSpec(
            name="file-record-agent",
            description=(
                "在任务运行工作区内按需判断是否读取可用上传快照，整理 records/ 过程记录，"
                "并将可交付结果写入 outputs/。"
            ),
            system_prompt=(
                "你只处理当前 run workspace 中的文件。uploads/ 是可选资料，只有任务需要时才读取；"
                "写入 records/ 或 outputs/。"
            ),
        ),
    ),
    expected_outputs=("deep-agent-*",),
    observability_labels={"file-record-agent": "文件记录"},
)


BID_MULTI_AGENT_PROFILE = AgentProfile(
    id=BID_MULTI_AGENT_PROFILE_ID,
    label="招投标多 Agent 分析",
    strategy="multi_agent",
    reason_code="multi_document_bid_comparison",
    system_prompt_fragment=(
        "围串标/投标比对任务应优先使用专业子 Agent 隔离推进：文件分类、要求匹配、"
        "投标人两两对比、证据归一化和报告写作。"
    ),
    subagents=(
        SubAgentSpec(
            name="document-classification-agent",
            description="识别 uploads/ 中招标文件、投标文件和其他附件，输出安全文件角色摘要。",
            system_prompt=(
                "只使用当前工作区文件工具。按文件名、标题和安全摘要判断材料角色；"
                "不要复制大段原文，结果写入 records/document-classification.md。"
            ),
        ),
        SubAgentSpec(
            name="requirement-matching-agent",
            description="抽取招标要求并检查各投标文件响应或共同偏离情况。",
            system_prompt=(
                "面向招标要求匹配，记录要求引用、响应缺口和共同偏离；"
                "输出只包含必要位置、短摘要和置信度。"
            ),
        ),
        SubAgentSpec(
            name="bidder-pair-comparison-agent",
            description="执行 A/B、A/C、B/C 等投标人两两对比，寻找报价、文本、模板和实体相似线索。",
            system_prompt=(
                "对投标人组合逐对检查。每个 pair 要么给出规范证据，要么说明未达到记录阈值；"
                "不要把工具返回原文当作最终结论。"
            ),
        ),
        SubAgentSpec(
            name="evidence-normalization-agent",
            description="把候选发现归一化为 canonical evidence.json 结构并检查 pair 覆盖。",
            system_prompt=(
                "规范化字段为 category、severity、title、description、bidders、pair、locations、"
                "requirement_reference、confidence、source_agent、rationale_summary；"
                "缺失值使用 null、[] 或 unknown。"
            ),
        ),
        SubAgentSpec(
            name="report-writing-agent",
            description="根据规范证据生成 outputs/report.html、final-summary.md 和 task-plan.md。",
            system_prompt=(
                "生成可交付报告文件到 outputs/；HTML 需要包含对比表、风险分组、pair 或投标人筛选线索和证据位置。"
            ),
        ),
    ),
    expected_outputs=("report.html", "final-summary.md", "evidence.json", "task-plan.md"),
    observability_labels={
        "document-classification-agent": "文件分类",
        "requirement-matching-agent": "要求匹配",
        "bidder-pair-comparison-agent": "投标人对比",
        "evidence-normalization-agent": "证据归一化",
        "report-writing-agent": "报告写作",
    },
)


AGENT_PROFILE_REGISTRY: dict[str, AgentProfile] = {
    DEFAULT_FILE_AGENT_PROFILE.id: DEFAULT_FILE_AGENT_PROFILE,
    BID_MULTI_AGENT_PROFILE.id: BID_MULTI_AGENT_PROFILE,
}


def validate_agent_profile(profile: AgentProfile) -> AgentProfile:
    _validate_identifier(profile.id, "profile.id", max_chars=80)
    _validate_text(profile.label, "profile.label", max_chars=80)
    _validate_text(profile.reason_code, "profile.reason_code", max_chars=120)
    _validate_text(profile.system_prompt_fragment, "profile.system_prompt_fragment", max_chars=1200)
    if profile.compiled_factory is not None:
        raise AgentProfileValidationError("V1 不启用 compiled_factory")
    _validate_tool_aliases(profile.allowed_tool_aliases)
    seen: set[str] = set()
    for subagent in profile.subagents:
        validate_subagent_spec(
            subagent,
            allowed_tool_aliases=profile.allowed_tool_aliases,
            model_override_policy=profile.model_override_policy,
        )
        if subagent.name in seen:
            raise AgentProfileValidationError(f"子 Agent 名称重复：{subagent.name}")
        seen.add(subagent.name)
    return profile


def validate_subagent_spec(
    spec: SubAgentSpec,
    *,
    allowed_tool_aliases: tuple[str, ...],
    model_override_policy: ModelOverridePolicy,
) -> SubAgentSpec:
    _validate_identifier(spec.name, "subagent.name", max_chars=80)
    _validate_text(spec.description, "subagent.description", max_chars=240)
    _validate_text(spec.system_prompt, "subagent.system_prompt", max_chars=1200)
    for alias in spec.tool_aliases:
        if alias not in allowed_tool_aliases:
            raise AgentProfileValidationError(f"子 Agent 工具别名未授权：{alias}")
    if spec.model is not None:
        if model_override_policy == "inherit_only":
            raise AgentProfileValidationError("当前 Agent Profile 不允许子 Agent 覆盖模型")
        if spec.model not in SAFE_MODEL_IDS:
            raise AgentProfileValidationError(f"子 Agent 模型未授权：{spec.model}")
    return spec


def get_agent_profile(profile_id: str) -> AgentProfile:
    try:
        return validate_agent_profile(AGENT_PROFILE_REGISTRY[profile_id])
    except KeyError:
        raise AgentProfileValidationError(f"未知 Agent Profile：{profile_id}") from None


def select_agent_profile(
    *,
    decision: IntentDecision,
    selected_upload_names: list[str],
    bidder_count: int,
    message: str,
) -> AgentProfile | None:
    if decision.route != "deep_agent":
        return None
    if (
        decision.reason in {"document_analysis_marker", "upload_reference_marker"}
        and bidder_count >= 2
        and is_bid_analysis_request(message)
        and len(selected_upload_names) >= 2
    ):
        return get_agent_profile(BID_MULTI_AGENT_PROFILE_ID)
    return get_agent_profile(DEFAULT_AGENT_PROFILE_ID)


def compile_subagents_for_deepagents(
    profile: AgentProfile,
    tool_registry: ToolRegistry,
) -> list[dict[str, Any]]:
    validate_agent_profile(profile)
    return [
        {
            "name": spec.name,
            "description": spec.description,
            "system_prompt": spec.system_prompt,
            "tools": _runtime_tools_for_subagent(spec, tool_registry),
            **({"model": spec.model} if spec.model else {}),
        }
        for spec in profile.subagents
    ]


def agent_profile_manifest(profile: AgentProfile | None) -> dict[str, Any] | None:
    if profile is None:
        return None
    return {
        "id": profile.id,
        "label": profile.label,
        "strategy": profile.strategy,
        "reason_code": profile.reason_code,
        "planned_subagents": profile.planned_subagents,
        "expected_outputs": list(profile.expected_outputs),
    }


def profile_decision_summary(profile: AgentProfile | None, bidder_count: int, route: str) -> str:
    if profile is None:
        if route == "search":
            return "简单搜索或天气请求使用单 Agent 工具调用加最终合成，不读取历史上传文件。"
        if route == "document_analysis":
            return "DeepAgent 不可用或显式文档兼容路径使用确定性文档分析流程。"
        return "普通对话使用单 Agent 回复。"
    if profile.id == BID_MULTI_AGENT_PROFILE_ID:
        return (
            f"检测到 {bidder_count} 份候选投标文件，任务需要多文档对比、证据归一化和报告输出，"
            "因此选择招投标多 Agent Profile。"
        )
    return "文件感知任务由主 Agent 判断是否读取上传快照，当前未达到并行子任务阈值。"


def _validate_identifier(value: str, field_name: str, *, max_chars: int) -> None:
    _validate_text(value, field_name, max_chars=max_chars)
    if not SAFE_PROFILE_ID_PATTERN.fullmatch(value):
        raise AgentProfileValidationError(f"{field_name} 只能包含字母、数字、点、下划线或短横线")


def _validate_text(value: str, field_name: str, *, max_chars: int) -> None:
    if not isinstance(value, str) or not value.strip():
        raise AgentProfileValidationError(f"{field_name} 不能为空")
    if len(value.strip()) > max_chars:
        raise AgentProfileValidationError(f"{field_name} 超过 {max_chars} 字符")


def _validate_tool_aliases(aliases: tuple[str, ...]) -> None:
    for alias in aliases:
        if alias not in SAFE_TOOL_ALIASES:
            raise AgentProfileValidationError(f"Agent Profile 工具别名未授权：{alias}")


def _runtime_tools_for_subagent(
    spec: SubAgentSpec,
    tool_registry: ToolRegistry,
) -> list[Callable[..., Any]]:
    tools: list[Callable[..., Any]] = []
    for alias in spec.tool_aliases:
        try:
            tools.append(tool_registry[alias])
        except KeyError:
            raise AgentProfileValidationError(f"子 Agent 工具别名缺少运行时实现：{alias}") from None
    return tools
