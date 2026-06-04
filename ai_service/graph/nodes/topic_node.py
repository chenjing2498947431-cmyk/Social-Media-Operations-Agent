"""Node A & Node B：选题生成 + 人工选题中断。"""
from __future__ import annotations

import logging

from langgraph.types import interrupt

from ai_service.core.metrics import track_node
from ai_service.graph.state import AgentState
from ai_service.tools.llm_client import get_llm_client
from ai_service.tools.web_search import get_mcp_bridge

logger = logging.getLogger(__name__)


@track_node("generate_topics")
async def generate_topics(state: AgentState) -> dict:
    """Node A: 让 LLM 自主决定是否联网搜索，然后生成备选选题。

    通过 MCPBridge 动态发现 MCP 服务器上的可用工具，让 LLM 自主选择
    调用哪个工具（如 brave_web_search / brave_local_search）。
    若 MCP 会话建立失败，降级为不使用搜索工具直接生成。
    """
    llm = get_llm_client()
    mcp = get_mcp_bridge()
    try:
        async with mcp.session() as session:
            topics, search_results = await llm.generate_topics(
                context=state.get("context", ""),
                mcp_session=session,
            )
    except Exception as exc:
        logger.warning("MCP 会话失败，降级为无搜索生成选题: %s", exc)
        topics, search_results = await llm.generate_topics(
            context=state.get("context", ""),
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
