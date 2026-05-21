"""Node C：根据选题流式生成长文草稿。

边生成边通过 LangGraph 的 custom stream writer 推送文本增量，
使 astream(stream_mode="custom") 的调用方可以实时拿到文案。
"""
from __future__ import annotations

from langgraph.config import get_stream_writer

from ai_service.core.metrics import track_node
from ai_service.graph.state import AgentState
from ai_service.tools.llm_client import get_llm_client


@track_node("generate_article")
async def generate_article(state: AgentState) -> dict:
    llm = get_llm_client()
    writer = get_stream_writer()

    chunks: list[str] = []
    async for delta in llm.stream_article(
        selected_topic=state["selected_topic"],
        context=state.get("context", ""),
    ):
        chunks.append(delta)
        writer({"type": "delta", "text": delta})

    return {
        "draft_article": "".join(chunks),
        "revision_round": 0,
        "status": "awaiting_review",
    }
