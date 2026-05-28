# fetch_news as Optional Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove `fetch_news` as a mandatory graph node and expose its functionality as an optional LLM tool inside `generate_topics`, so the model decides at runtime whether to perform a web search.

**Architecture:** `generate_topics` calls `LLMClient.generate_topics(context, search_fn)` with a `chat.completions.create` tool-calling loop (max 2 iterations): the LLM either calls `search_news` to fetch live data or returns topics directly. The graph becomes `START → generate_topics → human_select_topic`, and `fetch_news_node.py` is deleted.

**Tech Stack:** Python 3.14, LangGraph, OpenAI Python SDK (`chat.completions.create`), pytest (asyncio_mode=auto), unittest.mock

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Rewrite | `tests/test_llm_client_topics.py` | Tests for new `generate_topics` signature and tool-call loop |
| Modify | `ai_service/prompts/topic_prompts.yaml` | Remove `{search_context}` placeholder, add tool hint to system prompt |
| Modify | `ai_service/tools/llm_client.py` | Add `_SEARCH_NEWS_TOOL`, rewrite `generate_topics` with chat loop |
| Rewrite | `tests/test_topic_node.py` | Tests for updated node — injects `search_fn`, unpacks tuple |
| Modify | `ai_service/graph/nodes/topic_node.py` | Inject `search_fn`, unpack `(topics, search_results)` tuple |
| Delete | `tests/test_fetch_news_node.py` | Node is being removed |
| Delete | `ai_service/graph/nodes/fetch_news_node.py` | Node is being removed |
| Modify | `ai_service/graph/nodes/__init__.py` | Remove `fetch_news` import/export |
| Modify | `ai_service/graph/builder.py` | Remove `fetch_news` node, wire `START → generate_topics` directly |

---

## Task 1: Rewrite LLMClient.generate_topics (TDD)

**Files:**
- Rewrite: `tests/test_llm_client_topics.py`
- Modify: `ai_service/prompts/topic_prompts.yaml`
- Modify: `ai_service/tools/llm_client.py`

- [ ] **Step 1: Rewrite the test file**

Replace the entire contents of `tests/test_llm_client_topics.py` with:

```python
"""测试 LLMClient.generate_topics 的 tool-calling 行为。"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_service.tools.llm_client import LLMClient, _format_search_results


# ── helpers ──────────────────────────────────────────────────────────────────

def _msg(content=None, tool_calls=None):
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls
    return msg


def _tool_call(call_id, name, args_dict):
    tc = MagicMock()
    tc.id = call_id
    tc.function = MagicMock()
    tc.function.name = name
    tc.function.arguments = json.dumps(args_dict)
    return tc


def _response(message, prompt_tokens=10, completion_tokens=20):
    choice = MagicMock()
    choice.message = message
    resp = MagicMock()
    resp.choices = [choice]
    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens
    resp.usage = usage
    return resp


# ── _format_search_results ───────────────────────────────────────────────────

def test_format_empty_results_returns_fallback():
    assert _format_search_results([]) == "（搜索暂不可用，仅凭背景信息生成）"


def test_format_results_includes_title_and_snippet():
    results = [
        {"title": "美联储加息", "snippet": "加息25bp", "url": "https://a.com"},
        {"title": "A股下跌", "snippet": "沪指跌0.5%", "url": "https://b.com"},
    ]
    text = _format_search_results(results)
    assert "1. 美联储加息" in text
    assert "加息25bp" in text
    assert "https://a.com" in text
    assert "2. A股下跌" in text


# ── generate_topics ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_topics_returns_topics_when_llm_skips_tool():
    """LLM 拿到 search_fn 但直接返回内容时，used_results 为空列表。"""
    client = LLMClient()
    mock_oai = MagicMock()
    mock_oai.chat.completions.create = AsyncMock(
        return_value=_response(_msg(content='["选题A","选题B","选题C","选题D","选题E"]'))
    )
    mock_search = AsyncMock(return_value=[])

    with patch.object(client, "_get_client", return_value=mock_oai):
        topics, used_results = await client.generate_topics(
            context="美联储议息", search_fn=mock_search
        )

    assert topics == ["选题A", "选题B", "选题C", "选题D", "选题E"]
    assert used_results == []
    mock_search.assert_not_called()
    assert mock_oai.chat.completions.create.await_count == 1


@pytest.mark.asyncio
async def test_generate_topics_calls_search_tool_then_returns_topics():
    """LLM 调用 search_news 工具后，把结果注入对话，第二轮返回选题。"""
    client = LLMClient()
    mock_oai = MagicMock()

    tc = _tool_call("call_abc", "search_news", {"query": "美联储加息"})
    mock_oai.chat.completions.create = AsyncMock(
        side_effect=[
            _response(_msg(tool_calls=[tc])),
            _response(_msg(content='["选题A","选题B","选题C","选题D","选题E"]')),
        ]
    )
    search_results = [{"title": "美联储加息", "snippet": "加息25bp", "url": "https://a.com"}]
    mock_search = AsyncMock(return_value=search_results)

    with patch.object(client, "_get_client", return_value=mock_oai):
        topics, used_results = await client.generate_topics(
            context="美联储议息", search_fn=mock_search
        )

    assert topics == ["选题A", "选题B", "选题C", "选题D", "选题E"]
    assert used_results == search_results
    mock_search.assert_awaited_once_with("美联储加息")
    assert mock_oai.chat.completions.create.await_count == 2


@pytest.mark.asyncio
async def test_generate_topics_without_search_fn_omits_tools():
    """search_fn=None 时，请求中不附带 tools 参数。"""
    client = LLMClient()
    mock_oai = MagicMock()
    mock_oai.chat.completions.create = AsyncMock(
        return_value=_response(_msg(content='["选题A"]'))
    )

    with patch.object(client, "_get_client", return_value=mock_oai):
        topics, used_results = await client.generate_topics(context="黄金上涨")

    assert topics == ["选题A"]
    assert used_results == []
    call_kwargs = mock_oai.chat.completions.create.call_args.kwargs
    assert "tools" not in call_kwargs


@pytest.mark.asyncio
async def test_generate_topics_loop_exhausted_returns_empty():
    """两轮都返回 tool_calls 时，降级返回 ([], [])，不抛异常。"""
    client = LLMClient()
    mock_oai = MagicMock()

    tc = _tool_call("call_1", "search_news", {"query": "test"})
    mock_oai.chat.completions.create = AsyncMock(
        return_value=_response(_msg(tool_calls=[tc]))
    )
    mock_search = AsyncMock(return_value=[])

    with patch.object(client, "_get_client", return_value=mock_oai):
        topics, used_results = await client.generate_topics(
            context="测试", search_fn=mock_search
        )

    assert topics == []
    assert used_results == []
```

- [ ] **Step 2: Run tests to verify they FAIL (old implementation)**

```
cd financial_agent_project
pytest tests/test_llm_client_topics.py -v
```

Expected: the four `test_generate_topics_*` tests FAIL (old method returns `list[str]`, not a tuple; uses `_complete` not `chat.completions`). The two `test_format_*` tests should still PASS.

- [ ] **Step 3: Update `ai_service/prompts/topic_prompts.yaml`**

Replace the entire file with:

```yaml
# 选题生成 Prompt 配置
topic_generator:
  system: |
    你是一位资深的金融自媒体主编，擅长基于当日热点产出兼具流量与专业度的选题。
    你有一个 search_news 工具可以搜索最新金融新闻——当运营备注提供的背景信息
    不足以生成有时效性的选题时，主动调用它；否则直接基于现有信息生成。
    最终输出 5 个备选选题，每个不超过 30 字，避免标题党，但要具备话题性。
  user_template: |
    【运营背景备注】
    {context}

    请判断是否需要联网搜索最新金融热点，然后输出 5 个备选选题的 JSON 数组，例如：
    ["选题 A", "选题 B", "选题 C", "选题 D", "选题 E"]
```

- [ ] **Step 4: Rewrite `LLMClient.generate_topics` in `ai_service/tools/llm_client.py`**

At the top of the file, add `Callable` to the typing import:

```python
from typing import Any, AsyncIterator, Callable
```

After the existing `_parse_json_array` function (before the `LLMClient` class), add the tool constant:

```python
_SEARCH_NEWS_TOOL: dict = {
    "type": "function",
    "function": {
        "name": "search_news",
        "description": "搜索最新金融新闻和市场热点。当背景信息不足以生成有时效性的选题时调用。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"}
            },
            "required": ["query"],
        },
    },
}
```

Replace the existing `generate_topics` method (lines 126–138) with:

```python
async def generate_topics(
    self,
    context: str,
    search_fn: Callable | None = None,
) -> tuple[list[str], list[dict]]:
    """结合可选的联网工具生成候选选题列表。

    LLM 自主决定是否调用 search_news；最多循环 2 轮（1 次工具调用 + 1 次生成）。
    无论是否调用工具，均返回 (topics, used_results)。
    """
    prompt = get_prompt("topic_generator")
    system = prompt["system"].strip()
    user = prompt["user_template"].format(context=context).strip()

    messages: list[dict] = [{"role": "user", "content": user}]
    tools = [_SEARCH_NEWS_TOOL] if search_fn is not None else []
    used_results: list[dict] = []
    oai = self._get_client()

    for _ in range(2):
        create_kwargs: dict = {
            "model": self._settings.ark_model,
            "messages": [{"role": "system", "content": system}] + messages,
        }
        if tools:
            create_kwargs["tools"] = tools
            create_kwargs["tool_choice"] = "auto"

        response = await oai.chat.completions.create(**create_kwargs)

        usage = getattr(response, "usage", None)
        if usage is not None:
            record_token_usage(
                getattr(usage, "prompt_tokens", 0) or 0,
                getattr(usage, "completion_tokens", 0) or 0,
            )

        msg = response.choices[0].message

        if msg.tool_calls and search_fn is not None:
            messages.append({
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            })
            for tc in msg.tool_calls:
                args = json.loads(tc.function.arguments)
                results = await search_fn(args.get("query", context))
                used_results = results
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": _format_search_results(results),
                })
        else:
            text = (msg.content or "").strip()
            return _parse_json_array(text), used_results

    return [], used_results
```

- [ ] **Step 5: Run tests to verify they PASS**

```
cd financial_agent_project
pytest tests/test_llm_client_topics.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/test_llm_client_topics.py \
        ai_service/prompts/topic_prompts.yaml \
        ai_service/tools/llm_client.py
git commit -m "feat: rewrite generate_topics with optional search_news tool calling"
```

---

## Task 2: Update topic_node (TDD)

**Files:**
- Rewrite: `tests/test_topic_node.py`
- Modify: `ai_service/graph/nodes/topic_node.py`

- [ ] **Step 1: Rewrite `tests/test_topic_node.py`**

Replace the entire file with:

```python
"""generate_topics 节点单元测试。"""
from __future__ import annotations

from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from ai_service.graph.nodes.topic_node import generate_topics


@pytest.mark.asyncio
async def test_generate_topics_injects_search_fn_and_writes_state():
    """节点将 WebSearchTool.search 作为 search_fn 传给 LLM，并把返回值写入 state。"""
    state = {"context": "美联储议息", "status": "running", "node_metrics": []}

    with (
        patch("ai_service.graph.nodes.topic_node.get_llm_client") as mock_get_llm,
        patch("ai_service.graph.nodes.topic_node.get_web_search") as mock_get_search,
    ):
        mock_tool = MagicMock()
        mock_tool.search = AsyncMock()
        mock_get_search.return_value = mock_tool

        mock_llm = MagicMock()
        mock_llm.generate_topics = AsyncMock(
            return_value=(["选题A", "选题B", "选题C", "选题D", "选题E"], [])
        )
        mock_get_llm.return_value = mock_llm

        result = await generate_topics(state)

    mock_llm.generate_topics.assert_called_once_with(
        context="美联储议息",
        search_fn=mock_tool.search,
    )
    assert result["topics"] == ["选题A", "选题B", "选题C", "选题D", "选题E"]
    assert result["search_results"] == []
    assert result["status"] == "awaiting_topic"


@pytest.mark.asyncio
async def test_generate_topics_writes_search_results_when_tool_used():
    """LLM 使用了工具时，search_results 写入 state（非空）。"""
    state = {"context": "美联储议息", "status": "running", "node_metrics": []}
    used = [{"title": "美联储加息", "snippet": "加息25bp", "url": "https://a.com"}]

    with (
        patch("ai_service.graph.nodes.topic_node.get_llm_client") as mock_get_llm,
        patch("ai_service.graph.nodes.topic_node.get_web_search") as mock_get_search,
    ):
        mock_get_search.return_value = MagicMock()
        mock_llm = MagicMock()
        mock_llm.generate_topics = AsyncMock(return_value=(["选题A"], used))
        mock_get_llm.return_value = mock_llm

        result = await generate_topics(state)

    assert result["search_results"] == used


@pytest.mark.asyncio
async def test_generate_topics_passes_empty_string_when_context_missing():
    """state 中没有 context 时，传空字符串给 LLM，不报错。"""
    state = {"status": "running", "node_metrics": []}

    with (
        patch("ai_service.graph.nodes.topic_node.get_llm_client") as mock_get_llm,
        patch("ai_service.graph.nodes.topic_node.get_web_search") as mock_get_search,
    ):
        mock_get_search.return_value = MagicMock()
        mock_llm = MagicMock()
        mock_llm.generate_topics = AsyncMock(return_value=([], []))
        mock_get_llm.return_value = mock_llm

        result = await generate_topics(state)

    mock_llm.generate_topics.assert_called_once_with(context="", search_fn=ANY)
    assert result["topics"] == []
```

- [ ] **Step 2: Run tests to verify they FAIL**

```
cd financial_agent_project
pytest tests/test_topic_node.py -v
```

Expected: all 3 tests FAIL — old node passes `search_results=` kwarg and returns `list[str]` (no tuple), plus doesn't import `get_web_search`.

- [ ] **Step 3: Update `ai_service/graph/nodes/topic_node.py`**

Replace the entire file with:

```python
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
```

- [ ] **Step 4: Run tests to verify they PASS**

```
cd financial_agent_project
pytest tests/test_topic_node.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_topic_node.py ai_service/graph/nodes/topic_node.py
git commit -m "feat: update generate_topics node to inject search_fn and unpack tuple"
```

---

## Task 3: Remove fetch_news from the graph

**Files:**
- Delete: `tests/test_fetch_news_node.py`
- Delete: `ai_service/graph/nodes/fetch_news_node.py`
- Modify: `ai_service/graph/nodes/__init__.py`
- Modify: `ai_service/graph/builder.py`

- [ ] **Step 1: Delete `tests/test_fetch_news_node.py`**

```bash
git rm tests/test_fetch_news_node.py
```

- [ ] **Step 2: Delete `ai_service/graph/nodes/fetch_news_node.py`**

```bash
git rm ai_service/graph/nodes/fetch_news_node.py
```

- [ ] **Step 3: Update `ai_service/graph/nodes/__init__.py`**

Replace the entire file with:

```python
from .topic_node import generate_topics, human_select_topic
from .writer_node import generate_article
from .critic_node import human_review_article, revise_article
from .image_node import extract_image_content, generate_images, generate_xhs_copy

__all__ = [
    "generate_topics",
    "human_select_topic",
    "generate_article",
    "human_review_article",
    "revise_article",
    "extract_image_content",
    "generate_images",
    "generate_xhs_copy",
]
```

- [ ] **Step 4: Update `ai_service/graph/builder.py`**

Replace the entire file with:

```python
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
```

- [ ] **Step 5: Run the full test suite**

```
cd financial_agent_project
pytest -v
```

Expected: all remaining tests PASS. No import errors from the deleted `fetch_news_node`.

- [ ] **Step 6: Commit**

```bash
git add ai_service/graph/nodes/__init__.py ai_service/graph/builder.py
git commit -m "feat: remove fetch_news graph node — search is now an optional LLM tool"
```

---

## Verification

After all three tasks, confirm the refactor is complete:

```
cd financial_agent_project
pytest -v
```

Expected output: all tests pass, no references to `fetch_news_node` remain in the codebase.
