"""测试 analysis.py 和 model_provider.py 中的防御式访问修复。

覆盖：
- SubAgentWorker._inspect 对未知 category 抛出 ValueError（而非 KeyError）
- DeepSeekProvider._extract_content 对异常响应结构的防御式解析
"""

from __future__ import annotations

from unittest.mock import MagicMock, create_autospec

import httpx
import pytest

from app.analysis import (
    SubAgentSpec,
    SubAgentWorker,
)
from app.model_provider import DeepSeekProvider

# ---------------------------------------------------------------------------
# SubAgentWorker._inspect 未知类别
# ---------------------------------------------------------------------------


def _make_worker(category: str) -> SubAgentWorker:
    spec = SubAgentSpec(
        agent_id="test-agent",
        category=category,
        label="测试",
        prompt="test",
        tools=[],
        input_files=[],
    )
    controller = MagicMock()
    controller.is_cancelled.return_value = False
    return SubAgentWorker(
        spec=spec,
        tender_docs=[],
        bidder_docs=[],
        tools=MagicMock(),
        model="deepseek-reasoner",
        model_provider=MagicMock(),
        controller=controller,
        emit=MagicMock(),
    )


def test_inspect_unknown_category_raises_value_error() -> None:
    """未知类别应抛出 ValueError，而不是 KeyError。"""
    worker = _make_worker("nonexistent_category")
    with pytest.raises(ValueError, match="未知分析类别：nonexistent_category"):
        worker._inspect()


def test_inspect_known_category_does_not_raise_key_error() -> None:
    """已知类别不应因 dict 访问而抛 KeyError（会执行实际分析函数）。"""
    worker = _make_worker("quotation_similarity")
    # quotation_similarity 对空 bidder_docs 返回空列表
    result = worker._inspect()
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# DeepSeekProvider._extract_content 防御式解析
# ---------------------------------------------------------------------------


def _mock_response(payload: dict) -> httpx.Response:
    """构造一个包含指定 JSON payload 的 httpx.Response mock。"""
    response = create_autospec(httpx.Response, instance=True)
    response.json.return_value = payload
    return response


def test_extract_content_normal_response() -> None:
    """正常 OpenAI 格式响应应正确提取 content。"""
    response = _mock_response(
        {"choices": [{"message": {"role": "assistant", "content": "你好"}}]}
    )
    assert DeepSeekProvider._extract_content(response) == "你好"


def test_extract_content_missing_choices() -> None:
    """缺少 choices 字段应抛出 ValueError。"""
    response = _mock_response({})
    with pytest.raises(ValueError, match="响应缺少 choices 字段"):
        DeepSeekProvider._extract_content(response)


def test_extract_content_empty_choices() -> None:
    """空 choices 列表应抛出 ValueError。"""
    response = _mock_response({"choices": []})
    with pytest.raises(ValueError, match="响应缺少 choices 字段"):
        DeepSeekProvider._extract_content(response)


def test_extract_content_choices_not_list() -> None:
    """choices 不是列表应抛出 ValueError。"""
    response = _mock_response({"choices": "not a list"})
    with pytest.raises(ValueError, match="响应缺少 choices 字段"):
        DeepSeekProvider._extract_content(response)


def test_extract_content_missing_content() -> None:
    """message 中缺少 content 应抛出 ValueError。"""
    response = _mock_response({"choices": [{"message": {"role": "assistant"}}]})
    with pytest.raises(ValueError, match="响应缺少 content 字段"):
        DeepSeekProvider._extract_content(response)


def test_extract_content_content_is_none() -> None:
    """content 为 None 应抛出 ValueError。"""
    response = _mock_response(
        {"choices": [{"message": {"role": "assistant", "content": None}}]}
    )
    with pytest.raises(ValueError, match="响应缺少 content 字段"):
        DeepSeekProvider._extract_content(response)


def test_extract_content_missing_message_key() -> None:
    """choices[0] 中缺少 message 应抛出 ValueError。"""
    response = _mock_response({"choices": [{}]})
    with pytest.raises(ValueError, match="响应缺少 content 字段"):
        DeepSeekProvider._extract_content(response)


def test_extract_content_non_string_content() -> None:
    """content 为非字符串类型应通过 str() 转换返回。"""
    response = _mock_response(
        {"choices": [{"message": {"content": 42}}]}
    )
    assert DeepSeekProvider._extract_content(response) == "42"
