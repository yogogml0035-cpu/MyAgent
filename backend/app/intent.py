from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

TaskMode = Literal[
    "auto",
    "chat",
    "search",
    "document_analysis",
    "deep_agent",
    "bid_analysis",
]
InputScope = Literal["auto", "none", "task_uploads", "uploads"]
IntentRoute = Literal["chat", "search", "document_analysis", "deep_agent"]
ResolvedInputScope = Literal["none", "task_uploads"]
IntentName = Literal[
    "document_analysis",
    "continue_with_uploads",
    "weather",
    "search",
    "chat",
    "deep_agent",
    "forced_chat",
    "forced_search",
    "forced_document_analysis",
    "forced_deep_agent",
    "forced_uploads",
]


@dataclass(frozen=True)
class IntentDecision:
    mode: TaskMode
    input_scope: InputScope
    route: IntentRoute
    intent: IntentName
    resolved_input_scope: ResolvedInputScope
    use_uploads: bool
    requires_uploads: bool
    reason: str

    def as_manifest(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "name": self.intent,
            "route": self.route,
            "requires_uploads": self.requires_uploads,
            "reason": self.reason,
        }

    def input_scope_manifest(self) -> dict[str, str]:
        return {
            "requested": self.input_scope,
            "resolved": self.resolved_input_scope,
        }


BID_ANALYSIS_MARKERS = (
    "串标",
    "围标",
    "陪标",
    "投标",
    "招标",
    "标书",
    "投标文件",
    "招标文件",
    "报价",
    "报价清单",
    "雷同",
    "嫌疑",
    "供应商",
    "投标人",
    "bid",
    "bidding",
    "tender",
    "proposal",
    "quotation",
    "collusion",
)

UPLOAD_REFERENCE_MARKERS = (
    "继续",
    "接着",
    "上一轮",
    "上次",
    "刚才",
    "前面",
    "之前",
    "当前报告",
    "当前文件",
    "这些文件",
    "这些文档",
    "上述文件",
    "上述文档",
    "上传的文件",
    "上传的文档",
    "根据刚才",
    "根据这些",
    "根据上述",
    "重新总结",
    "总结当前报告",
)

WEATHER_MARKERS = (
    "天气",
    "气温",
    "温度",
    "下雨",
    "降雨",
    "空气质量",
    "weather",
    "forecast",
    "temperature",
)

SEARCH_MARKERS = (
    "搜索",
    "查一下",
    "查找",
    "检索",
    "联网",
    "最新",
    "新闻",
    "search",
    "lookup",
    "find",
    "news",
)


def route_intent(
    message: str,
    *,
    mode: TaskMode = "auto",
    input_scope: InputScope = "auto",
    has_uploads: bool = False,
) -> IntentDecision:
    normalized_mode = normalize_mode(mode)
    normalized_input_scope = normalize_input_scope(input_scope)

    if normalized_mode == "deep_agent":
        return IntentDecision(
            mode=mode,
            input_scope=input_scope,
            route="deep_agent",
            intent="forced_deep_agent",
            resolved_input_scope="task_uploads"
            if normalized_input_scope == "task_uploads" and has_uploads
            else "none",
            use_uploads=normalized_input_scope == "task_uploads" and has_uploads,
            requires_uploads=normalized_input_scope == "task_uploads",
            reason="mode_deep_agent",
        )

    if normalized_mode == "search":
        return IntentDecision(
            mode=mode,
            input_scope=input_scope,
            route="search",
            intent="forced_search",
            resolved_input_scope="none",
            use_uploads=False,
            requires_uploads=False,
            reason="mode_search",
        )

    if mode == "chat":
        return IntentDecision(
            mode=mode,
            input_scope=input_scope,
            route="chat",
            intent="forced_chat",
            resolved_input_scope="none",
            use_uploads=False,
            requires_uploads=False,
            reason="mode_chat",
        )

    if normalized_input_scope == "none":
        return IntentDecision(
            mode=mode,
            input_scope=input_scope,
            route="chat",
            intent="chat",
            resolved_input_scope="none",
            use_uploads=False,
            requires_uploads=False,
            reason="input_scope_none",
        )

    if normalized_mode == "document_analysis":
        return IntentDecision(
            mode=mode,
            input_scope=input_scope,
            route="document_analysis",
            intent="forced_document_analysis",
            resolved_input_scope="task_uploads" if has_uploads else "none",
            use_uploads=has_uploads,
            requires_uploads=True,
            reason="mode_document_analysis",
        )

    if normalized_input_scope == "task_uploads":
        return IntentDecision(
            mode=mode,
            input_scope=input_scope,
            route="document_analysis",
            intent="forced_uploads",
            resolved_input_scope="task_uploads" if has_uploads else "none",
            use_uploads=has_uploads,
            requires_uploads=True,
            reason="input_scope_task_uploads",
        )

    if is_weather_request(message):
        return IntentDecision(
            mode=mode,
            input_scope=input_scope,
            route="search",
            intent="weather",
            resolved_input_scope="none",
            use_uploads=False,
            requires_uploads=False,
            reason="weather_marker",
        )

    if is_search_request(message) and not references_existing_uploads(message):
        return IntentDecision(
            mode=mode,
            input_scope=input_scope,
            route="search",
            intent="search",
            resolved_input_scope="none",
            use_uploads=False,
            requires_uploads=False,
            reason="search_marker",
        )

    if has_uploads and references_existing_uploads(message):
        return IntentDecision(
            mode=mode,
            input_scope=input_scope,
            route="document_analysis",
            intent="continue_with_uploads",
            resolved_input_scope="task_uploads",
            use_uploads=True,
            requires_uploads=True,
            reason="upload_reference_marker",
        )

    if is_bid_analysis_request(message):
        return IntentDecision(
            mode=mode,
            input_scope=input_scope,
            route="document_analysis",
            intent="document_analysis",
            resolved_input_scope="task_uploads" if has_uploads else "none",
            use_uploads=has_uploads,
            requires_uploads=True,
            reason="document_analysis_marker",
        )

    return IntentDecision(
        mode=mode,
        input_scope=input_scope,
        route="chat",
        intent="chat",
        resolved_input_scope="none",
        use_uploads=False,
        requires_uploads=False,
        reason="default_chat",
    )


def is_bid_analysis_request(message: str) -> bool:
    return contains_marker(message, BID_ANALYSIS_MARKERS)


def references_existing_uploads(message: str) -> bool:
    return contains_marker(message, UPLOAD_REFERENCE_MARKERS)


def is_weather_request(message: str) -> bool:
    return contains_marker(message, WEATHER_MARKERS)


def is_search_request(message: str) -> bool:
    return contains_marker(message, SEARCH_MARKERS)


def contains_marker(message: str, markers: tuple[str, ...]) -> bool:
    lowered = message.casefold()
    return any(marker.casefold() in lowered for marker in markers)


def normalize_mode(mode: TaskMode) -> TaskMode:
    if mode == "bid_analysis":
        return "document_analysis"
    return mode


def normalize_input_scope(input_scope: InputScope) -> InputScope:
    if input_scope == "uploads":
        return "task_uploads"
    return input_scope
