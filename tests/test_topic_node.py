"""generate_topics 节点单元测试。"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from ai_service.graph.nodes.topic_node import generate_topics


@pytest.mark.asyncio
async def test_generate_topics_passes_search_results_from_state():
    """节点从 state.search_results 读取数据并传给 LLM。"""
    search_results = [
        {"title": "美联储加息", "snippet": "加息25bp", "url": "https://a.com"},
    ]
    state = {
        "context": "美联储议息",
        "search_results": search_results,
        "status": "running",
        "node_metrics": [],
    }

    with patch("ai_service.graph.nodes.topic_node.get_llm_client") as mock_get:
        mock_llm = AsyncMock()
        mock_llm.generate_topics = AsyncMock(return_value=["选题A", "选题B", "选题C", "选题D", "选题E"])
        mock_get.return_value = mock_llm

        result = await generate_topics(state)

    mock_llm.generate_topics.assert_called_once_with(
        context="美联储议息",
        search_results=search_results,
    )
    assert result["topics"] == ["选题A", "选题B", "选题C", "选题D", "选题E"]
    assert result["status"] == "awaiting_topic"


@pytest.mark.asyncio
async def test_generate_topics_handles_missing_search_results():
    """state 中没有 search_results 时，传 [] 给 LLM，不报错。"""
    state = {
        "context": "黄金创新高",
        "status": "running",
        "node_metrics": [],
    }

    with patch("ai_service.graph.nodes.topic_node.get_llm_client") as mock_get:
        mock_llm = AsyncMock()
        mock_llm.generate_topics = AsyncMock(return_value=["选题X"])
        mock_get.return_value = mock_llm

        result = await generate_topics(state)

    mock_llm.generate_topics.assert_called_once_with(
        context="黄金创新高",
        search_results=[],
    )
    assert result["topics"] == ["选题X"]
