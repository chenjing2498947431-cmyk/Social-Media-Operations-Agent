"""generate_xhs_copy 节点单元测试。"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from ai_service.graph.nodes.image_node import generate_xhs_copy


@pytest.mark.asyncio
async def test_generate_xhs_copy_writes_to_state():
    """节点正常执行时，xhs_copy 写入返回 dict，status=completed。"""
    state = {
        "selected_topic": "美联储加息对A股影响",
        "draft_article": "这是一篇长文...",
        "status": "running",
        "node_metrics": [],
    }

    with patch("ai_service.graph.nodes.image_node.get_llm_client") as mock_get:
        mock_llm = AsyncMock()
        mock_llm.generate_xhs_copy = AsyncMock(return_value="📈 测试文案\n\n#A股 #投资")
        mock_get.return_value = mock_llm

        result = await generate_xhs_copy(state)

    assert result["xhs_copy"] == "📈 测试文案\n\n#A股 #投资"
    assert result["status"] == "completed"
    mock_llm.generate_xhs_copy.assert_called_once_with(
        selected_topic="美联储加息对A股影响",
        draft_article="这是一篇长文...",
    )


@pytest.mark.asyncio
async def test_generate_xhs_copy_handles_missing_state_fields():
    """state 中没有 selected_topic / draft_article 时，传空字符串，不报错。"""
    state = {
        "status": "running",
        "node_metrics": [],
    }

    with patch("ai_service.graph.nodes.image_node.get_llm_client") as mock_get:
        mock_llm = AsyncMock()
        mock_llm.generate_xhs_copy = AsyncMock(return_value="文案")
        mock_get.return_value = mock_llm

        result = await generate_xhs_copy(state)

    mock_llm.generate_xhs_copy.assert_called_once_with(
        selected_topic="",
        draft_article="",
    )
    assert result["xhs_copy"] == "文案"
