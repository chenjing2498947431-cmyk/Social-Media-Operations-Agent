"""Node D & Node E：人工审核中断 + 改写节点。"""
from __future__ import annotations

from langgraph.types import interrupt

from ai_service.core.metrics import track_node
from ai_service.graph.state import AgentState
from ai_service.tools.llm_client import get_llm_client


def human_review_article(state: AgentState) -> dict:
    """Node D【中断点】：等待人工审核。

    恢复时调用方需传入 dict：
      {"decision": "approve"} 或
      {"decision": "reject", "feedback": "修改意见"}
    """
    review = interrupt(
        {
            "action": "review_article",
            "draft_article": state.get("draft_article"),
            "revision_round": state.get("revision_round", 0),
            "prompt": "请审核草稿：approve 通过 / reject 并填写 feedback",
        }
    )
    # review 形如 {"decision": "approve"} 或 {"decision": "reject", "feedback": "..."}
    decision = review.get("decision") if isinstance(review, dict) else None
    feedback = review.get("feedback") if isinstance(review, dict) else None

    return {
        "human_feedback": feedback if decision == "reject" else None,
        "status": "running" if decision == "approve" else "awaiting_review",
        # 把 decision 暂存到状态以便条件边读取
        "_last_decision": decision,
    }


@track_node("revise_article")
async def revise_article(state: AgentState) -> dict:
    """Node E：基于人工反馈进行重写，回到 Node D。"""
    llm = get_llm_client()
    revised = await llm.revise_article(
        draft_article=state.get("draft_article", ""),
        human_feedback=state.get("human_feedback", ""),
    )
    return {
        "draft_article": revised,
        "revision_round": state.get("revision_round", 0) + 1,
        "status": "awaiting_review",
        "_last_decision": None,
    }
