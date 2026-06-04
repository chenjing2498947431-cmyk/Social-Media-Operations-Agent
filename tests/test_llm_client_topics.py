"""测试 LLMClient.generate_topics 的 tool-calling 行为。"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_service.tools.llm_client import LLMClient, _format_search_results


# ── helpers ──────────────────────────────────────────────────────────────────

def _msg(content=None, tool_calls=None):
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls
    return msg


def _tool_call(call_id, name, args_dict):
    tc = MagicMock()
    tc.id = call_id
    tc.function = MagicMock()
    tc.function.name = name
    tc.function.arguments = json.dumps(args_dict)
    return tc


def _response(message, prompt_tokens=10, completion_tokens=20):
    choice = MagicMock()
    choice.message = message
    resp = MagicMock()
    resp.choices = [choice]
    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens
    resp.usage = usage
    return resp


# ── _format_search_results ───────────────────────────────────────────────────

def test_format_empty_results_returns_fallback():
    assert _format_search_results([]) == "（搜索暂不可用，仅凭背景信息生成）"


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


# ── generate_topics ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_topics_returns_topics_when_llm_skips_tool():
    """LLM 拿到 search_fn 但直接返回内容时，used_results 为空列表。"""
    client = LLMClient()
    mock_oai = MagicMock()
    mock_oai.chat.completions.create = AsyncMock(
        return_value=_response(_msg(content='{"topics": ["选题A","选题B","选题C","选题D","选题E"]}'))
    )
    mock_search = AsyncMock(return_value=[])

    with patch.object(client, "_get_client", return_value=mock_oai):
        topics, used_results = await client.generate_topics(
            context="美联储议息", search_fn=mock_search
        )

    assert topics == ["选题A", "选题B", "选题C", "选题D", "选题E"]
    assert used_results == []
    mock_search.assert_not_called()
    assert mock_oai.chat.completions.create.await_count == 1


@pytest.mark.asyncio
async def test_generate_topics_calls_search_tool_then_returns_topics():
    """LLM 调用 search_news 工具后，把结果注入对话，第二轮返回选题。"""
    client = LLMClient()
    mock_oai = MagicMock()

    tc = _tool_call("call_abc", "search_news", {"query": "美联储加息"})
    mock_oai.chat.completions.create = AsyncMock(
        side_effect=[
            _response(_msg(tool_calls=[tc])),
            _response(_msg(content='{"topics": ["选题A","选题B","选题C","选题D","选题E"]}')),
        ]
    )
    search_results = [{"title": "美联储加息", "snippet": "加息25bp", "url": "https://a.com"}]
    mock_search = AsyncMock(return_value=search_results)

    with patch.object(client, "_get_client", return_value=mock_oai):
        topics, used_results = await client.generate_topics(
            context="美联储议息", search_fn=mock_search
        )

    assert topics == ["选题A", "选题B", "选题C", "选题D", "选题E"]
    assert used_results == search_results
    mock_search.assert_awaited_once_with("美联储加息")
    assert mock_oai.chat.completions.create.await_count == 2


@pytest.mark.asyncio
async def test_generate_topics_without_search_fn_omits_tools():
    """search_fn=None 时，请求中不附带 tools 参数。"""
    client = LLMClient()
    mock_oai = MagicMock()
    mock_oai.chat.completions.create = AsyncMock(
        return_value=_response(_msg(content='{"topics": ["选题A"]}'))
    )

    with patch.object(client, "_get_client", return_value=mock_oai):
        topics, used_results = await client.generate_topics(context="黄金上涨")

    assert topics == ["选题A"]
    assert used_results == []
    call_kwargs = mock_oai.chat.completions.create.call_args.kwargs
    assert "tools" not in call_kwargs


@pytest.mark.asyncio
async def test_generate_topics_loop_exhausted_returns_empty():
    """两轮都返回 tool_calls 时，降级返回 ([], [])，不抛异常。"""
    client = LLMClient()
    mock_oai = MagicMock()

    tc = _tool_call("call_1", "search_news", {"query": "test"})
    mock_oai.chat.completions.create = AsyncMock(
        return_value=_response(_msg(tool_calls=[tc]))
    )
    mock_search = AsyncMock(return_value=[])

    with patch.object(client, "_get_client", return_value=mock_oai):
        topics, used_results = await client.generate_topics(
            context="测试", search_fn=mock_search
        )

    assert topics == []
    assert used_results == []
