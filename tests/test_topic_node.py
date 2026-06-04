"""generate_topics 节点单元测试。"""
from __future__ import annotations

from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from ai_service.graph.nodes.topic_node import generate_topics


def _make_mock_session():
    """构造一个可作为 async context manager 使用的 mock MCPSession。"""
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


@pytest.mark.asyncio
async def test_generate_topics_uses_mcp_session_and_writes_state():
    """节点通过 MCPBridge 创建 session 并传给 LLM，结果写入 state。"""
    state = {"context": "美联储议息", "status": "running", "node_metrics": []}
    mock_session = _make_mock_session()
    mock_bridge = MagicMock()
    mock_bridge.session = MagicMock(return_value=mock_session)

    mock_llm = MagicMock()
    mock_llm.generate_topics = AsyncMock(
        return_value=(["选题A", "选题B", "选题C", "选题D", "选题E"], [])
    )

    with (
        patch("ai_service.graph.nodes.topic_node.get_llm_client", return_value=mock_llm),
        patch("ai_service.graph.nodes.topic_node.get_mcp_bridge", return_value=mock_bridge),
    ):
        result = await generate_topics(state)

    mock_llm.generate_topics.assert_called_once_with(
        context="美联储议息",
        mcp_session=mock_session,
    )
    assert result["topics"] == ["选题A", "选题B", "选题C", "选题D", "选题E"]
    assert result["search_results"] == []
    assert result["status"] == "awaiting_topic"


@pytest.mark.asyncio
async def test_generate_topics_writes_search_results_when_tool_used():
    """LLM 使用了工具时，search_results 写入 state（非空）。"""
    state = {"context": "美联储议息", "status": "running", "node_metrics": []}
    used = [{"title": "美联储加息", "snippet": "加息25bp", "url": "https://a.com"}]
    mock_session = _make_mock_session()
    mock_bridge = MagicMock()
    mock_bridge.session = MagicMock(return_value=mock_session)

    mock_llm = MagicMock()
    mock_llm.generate_topics = AsyncMock(return_value=(["选题A"], used))

    with (
        patch("ai_service.graph.nodes.topic_node.get_llm_client", return_value=mock_llm),
        patch("ai_service.graph.nodes.topic_node.get_mcp_bridge", return_value=mock_bridge),
    ):
        result = await generate_topics(state)

    assert result["search_results"] == used


@pytest.mark.asyncio
async def test_generate_topics_passes_empty_string_when_context_missing():
    """state 中没有 context 时，传空字符串给 LLM，不报错。"""
    state = {"status": "running", "node_metrics": []}
    mock_session = _make_mock_session()
    mock_bridge = MagicMock()
    mock_bridge.session = MagicMock(return_value=mock_session)

    mock_llm = MagicMock()
    mock_llm.generate_topics = AsyncMock(return_value=([], []))

    with (
        patch("ai_service.graph.nodes.topic_node.get_llm_client", return_value=mock_llm),
        patch("ai_service.graph.nodes.topic_node.get_mcp_bridge", return_value=mock_bridge),
    ):
        result = await generate_topics(state)

    mock_llm.generate_topics.assert_called_once_with(context="", mcp_session=ANY)
    assert result["topics"] == []


@pytest.mark.asyncio
async def test_generate_topics_falls_back_when_mcp_session_fails():
    """MCPBridge.session().__aenter__ 抛异常时，降级为无搜索工具调用 LLM。"""
    state = {"context": "市场波动", "status": "running", "node_metrics": []}
    bad_session = AsyncMock()
    bad_session.__aenter__ = AsyncMock(side_effect=ConnectionRefusedError("MCP down"))
    bad_session.__aexit__ = AsyncMock(return_value=False)

    mock_bridge = MagicMock()
    mock_bridge.session = MagicMock(return_value=bad_session)

    mock_llm = MagicMock()
    mock_llm.generate_topics = AsyncMock(return_value=(["选题A"], []))

    with (
        patch("ai_service.graph.nodes.topic_node.get_llm_client", return_value=mock_llm),
        patch("ai_service.graph.nodes.topic_node.get_mcp_bridge", return_value=mock_bridge),
    ):
        result = await generate_topics(state)

    mock_llm.generate_topics.assert_called_once_with(context="市场波动")
    assert result["topics"] == ["选题A"]
    assert result["status"] == "awaiting_topic"
