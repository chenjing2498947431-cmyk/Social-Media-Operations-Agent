"""测试 generate_topics 方法和 _format_search_results 函数。"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from ai_service.tools.llm_client import LLMClient, _format_search_results


# ---------- _format_search_results ----------

def test_format_empty_results_returns_fallback():
    result = _format_search_results([])
    assert result == "（搜索暂不可用，仅凭背景信息生成）"


def test_format_results_includes_title_and_snippet():
    results = [
        {"title": "美联储加息", "snippet": "加息25bp", "url": "https://a.com"},
        {"title": "A股下跌", "snippet": "沪指跌0.5%", "url": "https://b.com"},
    ]
    text = _format_search_results(results)
    assert "1. 美联储加息" in text
    assert "加息25bp" in text
    assert "https://a.com" in text
    assert "2. A股下跌" in text


def test_format_results_handles_missing_fields():
    """snippet 或 url 缺失时不应抛出 KeyError。"""
    results = [{"title": "仅标题"}]
    text = _format_search_results(results)
    assert "1. 仅标题" in text


# ---------- generate_topics ----------

@pytest.mark.asyncio
async def test_generate_topics_passes_search_context_to_complete():
    """generate_topics 把格式化后的 search_context 传给 _complete。"""
    search_results = [
        {"title": "美联储加息", "snippet": "加息25bp", "url": "https://a.com"},
    ]
    client = LLMClient()

    with patch.object(client, "_complete", new_callable=AsyncMock) as mock_complete:
        mock_complete.return_value = '["选题A", "选题B", "选题C", "选题D", "选题E"]'
        topics = await client.generate_topics(
            context="美联储议息",
            search_results=search_results,
        )

    mock_complete.assert_called_once()
    call_kwargs = mock_complete.call_args[1]
    assert "search_context" in call_kwargs
    assert "美联储加息" in call_kwargs["search_context"]
    assert call_kwargs["context"] == "美联储议息"
    assert topics == ["选题A", "选题B", "选题C", "选题D", "选题E"]


@pytest.mark.asyncio
async def test_generate_topics_with_empty_search_results():
    """search_results 为空时，search_context 为降级文本，不报错。"""
    client = LLMClient()

    with patch.object(client, "_complete", new_callable=AsyncMock) as mock_complete:
        mock_complete.return_value = '["选题A", "选题B"]'
        topics = await client.generate_topics(context="美联储", search_results=[])

    call_kwargs = mock_complete.call_args[1]
    assert "搜索暂不可用" in call_kwargs["search_context"]
    assert topics == ["选题A", "选题B"]


@pytest.mark.asyncio
async def test_generate_topics_without_search_results_param():
    """search_results 默认为 None 时，降级处理，不报错。"""
    client = LLMClient()

    with patch.object(client, "_complete", new_callable=AsyncMock) as mock_complete:
        mock_complete.return_value = '["选题A"]'
        topics = await client.generate_topics(context="美联储")

    assert topics == ["选题A"]
