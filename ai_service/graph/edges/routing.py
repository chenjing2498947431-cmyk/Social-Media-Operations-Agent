"""条件路由逻辑。"""
from __future__ import annotations

from ai_service.graph.state import AgentState


def route_after_review(state: AgentState) -> str:
    """Node D 之后的条件边。

    返回值需对应 builder 里 add_conditional_edges 的映射 key。
    """
    decision = state.get("_last_decision")
    if decision == "approve":
        return "approve"
    return "reject"
