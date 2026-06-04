"""Node C：根据选题流式生成长文草稿。

边生成边通过 LangGraph 的 custom stream writer 推送文本增量，
使 astream(stream_mode="custom") 的调用方可以实时拿到文案。
"""
from __future__ import annotations

import logging

from langgraph.config import get_stream_writer

from ai_service.core.metrics import track_node
from ai_service.graph.state import AgentState
from ai_service.tools.llm_client import get_llm_client
from ai_service.tools.web_search import get_mcp_bridge

logger = logging.getLogger(__name__)


@track_node("generate_article")
async def generate_article(state: AgentState) -> dict:
    llm = get_llm_client()
    mcp = get_mcp_bridge()
    writer = get_stream_writer()

    selected_topic = state["selected_topic"]

    # 用选定选题搜一次最新资讯，为文章提供时效性素材
    article_search_results: list[dict] = []
    try:
        async with mcp.session() as session:
            article_search_results = await session.call_tool(
                "brave_news_search",
                {
                    "query": selected_topic,
                    "count": 8,
                    "search_lang": "zh-hans",
                    "country": "CN",
                    "freshness": "pw",
                },
            )
        logger.info("文章新闻搜索: %s | 结果数: %d", selected_topic, len(article_search_results))
    except Exception as exc:
        logger.warning("文章阶段新闻搜索失败: %s", exc)

    # 新闻搜索无结果时，回落到网页搜索
    if not article_search_results:
        try:
            async with mcp.session() as session:
                article_search_results = await session.call_tool(
                    "brave_web_search",
                    {"query": selected_topic, "count": 8},
                )
            logger.info("文章网页搜索(兜底): %s | 结果数: %d", selected_topic, len(article_search_results))
        except Exception as exc:
            logger.warning("文章阶段网页搜索失败: %s", exc)

    chunks: list[str] = []
    async for delta in llm.stream_article(
        selected_topic=selected_topic,
        context=state.get("context", ""),
        search_results=article_search_results,
    ):
        chunks.append(delta)
        writer({"type": "delta", "text": delta})

    return {
        "draft_article": "".join(chunks),
        "revision_round": 0,
        "status": "awaiting_review",
    }
