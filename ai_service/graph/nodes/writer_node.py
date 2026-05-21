"""Node C：根据选题生成长文草稿。"""
from __future__ import annotations

from ai_service.core.metrics import track_node
from ai_service.graph.state import AgentState
from ai_service.tools.llm_client import get_llm_client


@track_node("generate_article")
async def generate_article(state: AgentState) -> dict:
    llm = get_llm_client()
    draft = await llm.generate_article(
        selected_topic=state["selected_topic"],
        context=state.get("context", ""),
    )
    return {
        "draft_article": draft,
        "revision_round": 0,
        "status": "awaiting_review",
    }
