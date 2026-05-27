"""Node 0：联网搜索金融热点，结果存入 state.search_results。"""
from __future__ import annotations

import logging

from ai_service.core.metrics import track_node
from ai_service.graph.state import AgentState
from ai_service.tools.web_search import get_web_search

logger = logging.getLogger(__name__)


@track_node("fetch_news")
async def fetch_news(state: AgentState) -> dict:
    """以 state.context 为搜索词联网搜索，将结果写入 state.search_results。

    - 搜索成功：search_results = [{"title", "snippet", "url"}, ...]
    - 搜索失败：search_results = []，节点不抛错，generate_topics 降级处理
    """
    query = state["context"]
    tool = get_web_search()
    try:
        results = await tool.search(query, top_k=8)
    except Exception as exc:  # pragma: no cover – real WebSearchTool never raises
        logger.warning("fetch_news: search failed, degrading gracefully: %s", exc)
        results = []
    return {"search_results": results, "status": "running"}
