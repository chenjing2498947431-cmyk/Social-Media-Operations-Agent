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
            notify_resp = await client.post(
                self._mcp_url,
                headers=req_headers,
                json={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            )
            notify_resp.raise_for_status()

            # Step 3: tools/call brave_web_search
            search_resp = await client.post(
                self._mcp_url,
                headers=req_headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "brave_web_search",
                        "arguments": {"query": query, "count": top_k},
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
        entry: dict = {
            "title": news.get("title", ""),
            "snippet": news.get("description", ""),
            "url": news.get("url", ""),
        }
        age = news.get("age") or news.get("page_age")
        if age:
            entry["age"] = age
        results.append(entry)
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


def _mcp_tool_to_openai_fn(tool: dict[str, Any]) -> dict[str, Any]:
    """Convert an MCP tools/list entry to an OpenAI function definition dict."""
    return {
        "name": tool["name"],
        "description": tool.get("description", ""),
        "parameters": tool.get("inputSchema", {"type": "object", "properties": {}}),
    }


class MCPSession:
    """A single stateful MCP HTTP session.

    Keeps the httpx client open for the session lifetime so the server
    can correlate requests via the mcp-session-id header.

    Usage::

        async with MCPSession(url) as session:
            tools = await session.list_tools()
            items = await session.call_tool("brave_web_search", {"query": "..."})
    """

    def __init__(self, mcp_url: str) -> None:
        self._mcp_url = mcp_url
        self._session_id: str | None = None
        self._client: Any = None  # httpx.AsyncClient
        self._req_id: int = 0

    async def __aenter__(self) -> "MCPSession":
        import httpx as _httpx
        self._client = _httpx.AsyncClient(timeout=15)
        try:
            await self._initialize()
        except Exception:
            await self._client.aclose()
            self._client = None
            raise
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _next_id(self) -> int:
        self._req_id += 1
        return self._req_id

    def _req_headers(self) -> dict[str, str]:
        h = dict(_MCP_HEADERS)
        if self._session_id:
            h["mcp-session-id"] = self._session_id
        return h

    async def _initialize(self) -> None:
        resp = await self._client.post(
            self._mcp_url,
            headers=_MCP_HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "ai-service", "version": "1.0"},
                },
            },
        )
        resp.raise_for_status()
        self._session_id = resp.headers.get("mcp-session-id")
        await self._client.post(
            self._mcp_url,
            headers=self._req_headers(),
            json={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        )

    async def list_tools(self) -> list[dict[str, Any]]:
        """Return available MCP tools as OpenAI-compatible function definitions.

        Returns an empty list on failure so the caller can degrade gracefully.
        """
        try:
            resp = await self._client.post(
                self._mcp_url,
                headers=self._req_headers(),
                json={
                    "jsonrpc": "2.0",
                    "id": self._next_id(),
                    "method": "tools/list",
                    "params": {},
                },
            )
            resp.raise_for_status()
            data = _parse_sse(resp.text)
            if not data:
                return []
            tools = data.get("result", {}).get("tools", [])
            return [_mcp_tool_to_openai_fn(t) for t in tools]
        except Exception as exc:
            logger.warning("MCPSession.list_tools 失败: %s", exc)
            return []

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> list[dict[str, Any]]:
        """Call an MCP tool; return parsed news items [{title, snippet, url}, ...].

        Returns an empty list on failure so the caller can degrade gracefully.
        """
        try:
            resp = await self._client.post(
                self._mcp_url,
                headers=self._req_headers(),
                json={
                    "jsonrpc": "2.0",
                    "id": self._next_id(),
                    "method": "tools/call",
                    "params": {"name": name, "arguments": arguments},
                },
            )
            resp.raise_for_status()
            data = _parse_sse(resp.text)
            if not data:
                return []
            return _extract_news(data, top_k=8)
        except Exception as exc:
            logger.warning("MCPSession.call_tool(%s) 失败: %s", name, exc)
            return []


class MCPBridge:
    """Factory that creates MCP sessions against a configured server URL."""

    def __init__(self, mcp_url: str | None = None) -> None:
        self._mcp_url = mcp_url or get_settings().brave_mcp_url

    def session(self) -> MCPSession:
        """Return a new async context-manager session."""
        return MCPSession(self._mcp_url)


_bridge: MCPBridge | None = None


def get_mcp_bridge() -> MCPBridge:
    global _bridge
    if _bridge is None:
        _bridge = MCPBridge()
    return _bridge


def reset_mcp_bridge() -> None:
    """测试用：清掉单例。"""
    global _bridge
    _bridge = None
