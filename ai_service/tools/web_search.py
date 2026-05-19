"""预留的联网搜索工具，用于未来抓取金融实时数据。
当前为占位实现，不会被节点调用。"""
from __future__ import annotations

from typing import Any


class WebSearchTool:
    async def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        return [
            {"title": f"[mock] {query} - 结果 {i+1}", "url": f"https://example.com/{i}"}
            for i in range(top_k)
        ]


_search: WebSearchTool | None = None


def get_web_search() -> WebSearchTool:
    global _search
    if _search is None:
        _search = WebSearchTool()
    return _search
