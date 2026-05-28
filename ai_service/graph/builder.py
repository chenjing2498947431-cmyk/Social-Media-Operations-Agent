"""LangGraph StateGraph 组装。"""
from __future__ import annotations

from langgraph.graph import StateGraph, START, END

from ai_service.graph.state import AgentState
from ai_service.graph.nodes import (
    generate_topics,
    human_select_topic,
    generate_article,
    human_review_article,
    revise_article,
    extract_image_content,
    generate_images,
    generate_xhs_copy,
)
from ai_service.graph.edges import route_after_review
from ai_service.persistence.checkpointer import get_checkpointer


def build_graph():
    builder = StateGraph(AgentState)

    builder.add_node("generate_topics", generate_topics)
    builder.add_node("human_select_topic", human_select_topic)
    builder.add_node("generate_article", generate_article)
    builder.add_node("human_review_article", human_review_article)
    builder.add_node("revise_article", revise_article)
    builder.add_node("extract_image_content", extract_image_content)
    builder.add_node("generate_images", generate_images)
    builder.add_node("generate_xhs_copy", generate_xhs_copy)

    builder.add_edge(START, "generate_topics")
    builder.add_edge("generate_topics", "human_select_topic")
    builder.add_edge("human_select_topic", "generate_article")
    builder.add_edge("generate_article", "human_review_article")

    builder.add_conditional_edges(
        "human_review_article",
        route_after_review,
        {
            "approve": "extract_image_content",
            "reject": "revise_article",
        },
    )
    builder.add_edge("revise_article", "human_review_article")
    builder.add_edge("extract_image_content", "generate_images")
    builder.add_edge("generate_images", "generate_xhs_copy")
    builder.add_edge("generate_xhs_copy", END)

    return builder.compile(checkpointer=get_checkpointer())


_compiled_graph = None


def get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph


def reset_graph() -> None:
    """重新装配图（用于 checkpointer 重置后）。"""
    global _compiled_graph
    _compiled_graph = None
