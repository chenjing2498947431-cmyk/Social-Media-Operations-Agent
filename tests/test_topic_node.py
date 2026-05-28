"""generate_topics 节点单元测试。"""
from __future__ import annotations

from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from ai_service.graph.nodes.topic_node import generate_topics


@pytest.mark.asyncio
async def test_generate_topics_injects_search_fn_and_writes_state():
    """节点将 WebSearchTool.search 作为 search_fn 传给 LLM，并把返回值写入 state。"""
    state = {"context": "美联储议息", "status": "running", "node_metrics": []}

    with (
        patch("ai_service.graph.nodes.topic_node.get_llm_client") as mock_get_llm,
        patch("ai_service.graph.nodes.topic_node.get_web_search") as mock_get_search,
    ):
        mock_tool = MagicMock()
        mock_tool.search = AsyncMock()
        mock_get_search.return_value = mock_tool

        mock_llm = MagicMock()
        mock_llm.generate_topics = AsyncMock(
            return_value=(["选题A", "选题B", "选题C", "选题D", "选题E"], [])
        )
        mock_get_llm.return_value = mock_llm

        result = await generate_topics(state)

    mock_llm.generate_topics.assert_called_once_with(
        context="美联储议息",
        search_fn=mock_tool.search,
    )
    assert result["topics"] == ["选题A", "选题B", "选题C", "选题D", "选题E"]
    assert result["search_results"] == []
    assert result["status"] == "awaiting_topic"


@pytest.mark.asyncio
async def test_generate_topics_writes_search_results_when_tool_used():
    """LLM 使用了工具时，search_results 写入 state（非空）。"""
    state = {"context": "美联储议息", "status": "running", "node_metrics": []}
    used = [{"title": "美联储加息", "snippet": "加息25bp", "url": "https://a.com"}]

    with (
        patch("ai_service.graph.nodes.topic_node.get_llm_client") as mock_get_llm,
        patch("ai_service.graph.nodes.topic_node.get_web_search") as mock_get_search,
    ):
        mock_get_search.return_value = MagicMock()
        mock_llm = MagicMock()
        mock_llm.generate_topics = AsyncMock(return_value=(["选题A"], used))
        mock_get_llm.return_value = mock_llm

        result = await generate_topics(state)

    assert result["search_results"] == used


@pytest.mark.asyncio
async def test_generate_topics_passes_empty_string_when_context_missing():
    """state 中没有 context 时，传空字符串给 LLM，不报错。"""
    state = {"status": "running", "node_metrics": []}

    with (
        patch("ai_service.graph.nodes.topic_node.get_llm_client") as mock_get_llm,
        patch("ai_service.graph.nodes.topic_node.get_web_search") as mock_get_search,
    ):
        mock_get_search.return_value = MagicMock()
        mock_llm = MagicMock()
        mock_llm.generate_topics = AsyncMock(return_value=([], []))
        mock_get_llm.return_value = mock_llm

        result = await generate_topics(state)

    mock_llm.generate_topics.assert_called_once_with(context="", search_fn=ANY)
    assert result["topics"] == []
