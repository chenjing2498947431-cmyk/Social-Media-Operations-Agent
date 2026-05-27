"""验证 AgentState 包含 search_results 字段。"""
from ai_service.graph.state import AgentState


def test_agent_state_has_search_results():
    """search_results 字段存在且可赋值为 list[dict]。"""
    state: AgentState = {
        "context": "美联储加息",
        "search_results": [{"title": "标题", "snippet": "摘要", "url": "https://a.com"}],
        "topics": [],
        "status": "running",
        "node_metrics": [],
    }
    assert isinstance(state["search_results"], list)
    assert state["search_results"][0]["title"] == "标题"


def test_agent_state_search_results_defaults_to_absent():
    """search_results 是 total=False 字段，可以不传。"""
    state: AgentState = {"context": "美联储", "status": "running", "node_metrics": []}
    assert state.get("search_results") is None


def test_xhs_copy_field_in_agent_state():
    """xhs_copy 字段存在于 AgentState 注解中。"""
    import typing
    hints = typing.get_type_hints(AgentState)
    assert "xhs_copy" in hints
