"""Tests for LLMClient.generate_xhs_copy."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from ai_service.tools.llm_client import LLMClient


@pytest.mark.asyncio
async def test_generate_xhs_copy_calls_correct_prompt():
    """generate_xhs_copy 以 xhs_copy_writer 为 prompt 名，传入 selected_topic 和 draft_article。"""
    client = LLMClient()

    with patch.object(client, "_complete", new_callable=AsyncMock) as mock_complete:
        mock_complete.return_value = "📈 测试标题\n\n正文内容\n\n#A股 #测试"
        result = await client.generate_xhs_copy(
            selected_topic="美联储加息对A股影响",
            draft_article="这是一篇关于美联储的长文...",
        )

    mock_complete.assert_called_once_with(
        "xhs_copy_writer",
        selected_topic="美联储加息对A股影响",
        draft_article="这是一篇关于美联储的长文...",
    )
    assert result == "📈 测试标题\n\n正文内容\n\n#A股 #测试"


@pytest.mark.asyncio
async def test_generate_xhs_copy_returns_string():
    """返回值是字符串，直接透传 _complete 的结果。"""
    client = LLMClient()

    with patch.object(client, "_complete", new_callable=AsyncMock) as mock_complete:
        mock_complete.return_value = "小红书文案内容"
        result = await client.generate_xhs_copy(
            selected_topic="选题",
            draft_article="长文",
        )

    assert isinstance(result, str)
    assert result == "小红书文案内容"
