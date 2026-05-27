"""WebSearchTool 单元测试：mock httpx，验证 MCP 协议流程和结果解析。"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_service.tools.web_search import WebSearchTool


def _sse(payload: dict) -> str:
    """构造 SSE 响应文本。"""
    return f"event: message\ndata: {json.dumps(payload)}\n\n"


def _make_mock_response(status: int, text: str, headers: dict | None = None) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.text = text
    r.headers = headers or {}
    r.raise_for_status = MagicMock()
    return r


@pytest.mark.asyncio
async def test_search_returns_parsed_results():
    """search() 成功时返回解析好的 list[dict]。"""
    init_payload = {"result": {"protocolVersion": "2024-11-05", "serverInfo": {}}}
    news_items = [
        {"url": "https://a.com", "title": "美联储加息", "description": "加息25bp", "age": "1 hour ago"},
        {"url": "https://b.com", "title": "A股下跌", "description": "沪指跌0.5%", "age": "2 hours ago"},
    ]
    search_payload = {
        "result": {
            "content": [
                {"type": "text", "text": json.dumps(item)} for item in news_items
            ]
        }
    }

    mock_init_resp = _make_mock_response(200, _sse(init_payload), {"mcp-session-id": "sess-123"})
    mock_notify_resp = _make_mock_response(202, "")
    mock_search_resp = _make_mock_response(200, _sse(search_payload))

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=[mock_init_resp, mock_notify_resp, mock_search_resp])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    tool = WebSearchTool(mcp_url="http://localhost:8200/mcp")
    with patch("ai_service.tools.web_search.httpx.AsyncClient", return_value=mock_client):
        results = await tool.search("美联储", top_k=5)

    assert len(results) == 2
    assert results[0]["title"] == "美联储加息"
    assert results[0]["snippet"] == "加息25bp"
    assert results[0]["url"] == "https://a.com"
    assert results[1]["title"] == "A股下跌"


@pytest.mark.asyncio
async def test_search_passes_session_id_in_subsequent_requests():
    """initialize 返回 mcp-session-id 后，后续请求必须携带该 header。"""
    init_payload = {"result": {}}
    search_payload = {"result": {"content": []}}

    mock_init_resp = _make_mock_response(200, _sse(init_payload), {"mcp-session-id": "my-session-id"})
    mock_notify_resp = _make_mock_response(202, "")
    mock_search_resp = _make_mock_response(200, _sse(search_payload))

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=[mock_init_resp, mock_notify_resp, mock_search_resp])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    tool = WebSearchTool(mcp_url="http://localhost:8200/mcp")
    with patch("ai_service.tools.web_search.httpx.AsyncClient", return_value=mock_client):
        await tool.search("测试", top_k=3)

    # notifications/initialized call (index 1) should have session header
    notify_call_kwargs = mock_client.post.call_args_list[1][1]
    assert notify_call_kwargs["headers"].get("mcp-session-id") == "my-session-id"

    # tools/call (index 2) should also have session header
    search_call_kwargs = mock_client.post.call_args_list[2][1]
    assert search_call_kwargs["headers"].get("mcp-session-id") == "my-session-id"


@pytest.mark.asyncio
async def test_search_respects_top_k():
    """search() 返回结果数量不超过 top_k。"""
    news_items = [
        {"url": f"https://{i}.com", "title": f"新闻{i}", "description": f"摘要{i}", "age": "1h"}
        for i in range(10)
    ]
    search_payload = {
        "result": {"content": [{"type": "text", "text": json.dumps(item)} for item in news_items]}
    }
    mock_init_resp = _make_mock_response(200, _sse({"result": {}}), {"mcp-session-id": "s"})
    mock_notify_resp = _make_mock_response(202, "")
    mock_search_resp = _make_mock_response(200, _sse(search_payload))

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=[mock_init_resp, mock_notify_resp, mock_search_resp])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    tool = WebSearchTool(mcp_url="http://localhost:8200/mcp")
    with patch("ai_service.tools.web_search.httpx.AsyncClient", return_value=mock_client):
        results = await tool.search("测试", top_k=3)

    assert len(results) == 3


@pytest.mark.asyncio
async def test_search_returns_empty_on_http_error():
    """HTTP 异常时返回空列表，不抛出异常。"""
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=Exception("Connection refused"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    tool = WebSearchTool(mcp_url="http://localhost:8200/mcp")
    with patch("ai_service.tools.web_search.httpx.AsyncClient", return_value=mock_client):
        results = await tool.search("测试", top_k=5)

    assert results == []


@pytest.mark.asyncio
async def test_search_returns_empty_on_malformed_sse():
    """服务器返回 200 但 body 中没有 data: 行时，返回空列表。"""
    mock_init_resp = _make_mock_response(200, _sse({"result": {}}), {"mcp-session-id": "s"})
    mock_notify_resp = _make_mock_response(202, "")
    # SSE 响应只有 event 行，没有 data: 行
    mock_search_resp = _make_mock_response(200, "event: message\n\n")

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=[mock_init_resp, mock_notify_resp, mock_search_resp])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    tool = WebSearchTool(mcp_url="http://localhost:8200/mcp")
    with patch("ai_service.tools.web_search.httpx.AsyncClient", return_value=mock_client):
        results = await tool.search("测试", top_k=5)

    assert results == []
