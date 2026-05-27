"""Brave Search MCP Server 客户端。

通过标准 MCP HTTP 协议（initialize → notifications/initialized → tools/call）
调用本地 brave-search-mcp-server，返回新闻列表。

启动 MCP Server：
    BRAVE_API_KEY=<key> npx -y @brave/brave-search-mcp-server --transport http --port 8200

环境变量：
    BRAVE_MCP_URL  MCP Server 的 /mcp 端点（默认 http://localhost:8200/mcp）
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from ai_service.core.config import get_settings

logger = logging.getLogger(__name__)

_MCP_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


class WebSearchTool:
    """通过 MCP HTTP 协议调用 Brave Search 的新闻搜索工具。"""

    def __init__(self, mcp_url: str | None = None) -> None:
        self._mcp_url = mcp_url or get_settings().brave_mcp_url

    async def search(self, query: str, top_k: int = 8) -> list[dict[str, Any]]:
        """搜索新闻，返回 [{"title": str, "snippet": str, "url": str}, ...]。

        失败时返回空列表，不抛出异常（调用方降级处理）。
        """
        try:
            return await self._do_search(query, top_k)
        except Exception as exc:
            logger.warning("WebSearchTool.search 失败，返回空结果: %s", exc)
            return []

    async def _do_search(self, query: str, top_k: int) -> list[dict[str, Any]]:
        """实际执行 MCP 三步协议。"""
        async with httpx.AsyncClient(timeout=15) as client:
            # Step 1: initialize
            init_resp = await client.post(
                self._mcp_url,
                headers=_MCP_HEADERS,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "ai-service", "version": "1.0"},
                    },
                },
            )
            init_resp.raise_for_status()
            session_id = init_resp.headers.get("mcp-session-id")

            # 后续请求携带 session id
            req_headers = dict(_MCP_HEADERS)
            if session_id:
                req_headers["mcp-session-id"] = session_id

            # Step 2: notifications/initialized
            await client.post(
                self._mcp_url,
                headers=req_headers,
                json={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            )

            # Step 3: tools/call brave_news_search
            search_resp = await client.post(
                self._mcp_url,
                headers=req_headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "brave_news_search",
                        "arguments": {"query": query, "count": top_k, "freshness": "pd"},
                    },
                },
            )
            search_resp.raise_for_status()
            # Parse SSE inside the context manager so the response body is
            # guaranteed to be available (safe even now since httpx buffers
            # fully, but explicit is better than implicit).
            data = _parse_sse(search_resp.text)

        if not data:
            return []
        return _extract_news(data, top_k)


def _parse_sse(text: str) -> dict[str, Any] | None:
    """从 SSE 格式响应文本中提取并解析第一条 data: 行。"""
    for line in text.splitlines():
        if line.startswith("data:"):
            try:
                return json.loads(line[5:].strip())
            except json.JSONDecodeError:
                pass
    return None


def _extract_news(data: dict[str, Any], top_k: int) -> list[dict[str, Any]]:
    """从 MCP tools/call 响应中提取新闻列表。

    MCP 响应结构：
        {"result": {"content": [{"type": "text", "text": "{...json...}"}, ...]}}
    每条 text 是一个 JSON 字符串，字段包含 title / description / url。
    """
    content = data.get("result", {}).get("content", [])
    results: list[dict[str, Any]] = []
    for item in content:
        if item.get("type") != "text":
            continue
        try:
            news = json.loads(item["text"])
        except (json.JSONDecodeError, KeyError):
            continue
        results.append({
            "title": news.get("title", ""),
            "snippet": news.get("description", ""),
            "url": news.get("url", ""),
        })
        if len(results) >= top_k:
            break
    return results


_search: WebSearchTool | None = None


def get_web_search() -> WebSearchTool:
    global _search
    if _search is None:
        _search = WebSearchTool()
    return _search


def reset_web_search() -> None:
    """测试用：清掉单例。"""
    global _search
    _search = None
