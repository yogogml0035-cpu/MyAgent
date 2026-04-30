"""Local Harness skeletons kept separate from the legacy TaskRunner."""

from .context_manager import DefaultContextManager, context_selection_payload
from .engine import ProjectingHarnessEngine
from .gateway import (
    GatewayTool,
    LegacyExecutionGateway,
    artifact_resource_ref,
    legacy_bid_analysis_executor,
    legacy_deep_agent_executor,
    legacy_web_search_executor,
    upload_resource_ref,
)
from .scheduler import InlineScheduler

__all__ = [
    "DefaultContextManager",
    "GatewayTool",
    "InlineScheduler",
    "LegacyExecutionGateway",
    "ProjectingHarnessEngine",
    "artifact_resource_ref",
    "legacy_bid_analysis_executor",
    "legacy_deep_agent_executor",
    "legacy_web_search_executor",
    "context_selection_payload",
    "upload_resource_ref",
]
