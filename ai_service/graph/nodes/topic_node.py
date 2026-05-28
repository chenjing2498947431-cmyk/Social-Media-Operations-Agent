"""Node A & Node B：选题生成 + 人工选题中断。"""
from __future__ import annotations

from langgraph.types import interrupt

from ai_service.core.metrics import track_node
from ai_service.graph.state import AgentState
from ai_service.tools.llm_client import get_llm_client
from ai_service.tools.web_search import get_web_search


@track_node("generate_topics")
async def generate_topics(state: AgentState) -> dict:
    """Node A: 让 LLM 自主决定是否联网搜索，然后生成备选选题。"""
    llm = get_llm_client()
    search_tool = get_web_search()
    topics, search_results = await llm.generate_topics(
        context=state.get("context", ""),
        search_fn=search_tool.search,
    )
    return {
        "topics": topics,
        "search_results": search_results,
        "status": "awaiting_topic",
    }


def human_select_topic(state: AgentState) -> dict:
    """Node B【中断点】：等待人工选择选题。

    interrupt() 会暂停图执行，返回给调用方 'topics'，
    待调用方通过 Command(resume="选定的选题") 恢复后继续。
    """
    selected = interrupt(
        {
            "action": "select_topic",
            "topics": state.get("topics", []),
            "prompt": "请从备选选题中选择一个，或直接输入新选题",
        }
    )
    return {
        "selected_topic": selected,
        "status": "running",
    }
