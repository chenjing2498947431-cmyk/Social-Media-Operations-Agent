"""fetch_news 节点单元测试。"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from ai_service.graph.nodes.fetch_news_node import fetch_news


@pytest.mark.asyncio
async def test_fetch_news_writes_results_to_state():
    """搜索成功时，search_results 写入返回 dict。"""
    mock_results = [
        {"title": "美联储加息", "snippet": "加息25bp", "url": "https://a.com"},
        {"title": "A股下跌", "snippet": "沪指跌0.5%", "url": "https://b.com"},
    ]
    state = {"context": "美联储加息预期", "status": "running", "node_metrics": []}

    with patch("ai_service.graph.nodes.fetch_news_node.get_web_search") as mock_get:
        mock_tool = AsyncMock()
        mock_tool.search = AsyncMock(return_value=mock_results)
        mock_get.return_value = mock_tool

        result = await fetch_news(state)

    assert result["search_results"] == mock_results
    assert result["status"] == "running"
    mock_tool.search.assert_called_once_with("美联储加息预期", top_k=8)


@pytest.mark.asyncio
async def test_fetch_news_uses_context_as_query():
    """确认 search() 的 query 参数来自 state['context']。"""
    state = {"context": "黄金创新高 通胀数据", "status": "running", "node_metrics": []}

    with patch("ai_service.graph.nodes.fetch_news_node.get_web_search") as mock_get:
        mock_tool = AsyncMock()
        mock_tool.search = AsyncMock(return_value=[])
        mock_get.return_value = mock_tool

        await fetch_news(state)

    mock_tool.search.assert_called_once_with("黄金创新高 通胀数据", top_k=8)


@pytest.mark.asyncio
async def test_fetch_news_degrades_gracefully_on_search_failure():
    """搜索异常时，search_results 为空列表，节点不抛出异常。"""
    state = {"context": "测试", "status": "running", "node_metrics": []}

    with patch("ai_service.graph.nodes.fetch_news_node.get_web_search") as mock_get:
        mock_tool = AsyncMock()
        mock_tool.search = AsyncMock(side_effect=Exception("网络超时"))
        mock_get.return_value = mock_tool

        # WebSearchTool.search 内部已 catch，此处不应抛出
        result = await fetch_news(state)

    assert result["search_results"] == []
