# Design: fetch_news as Optional Tool for generate_topics

**Date:** 2026-05-28  
**Status:** Approved

## Overview

Convert `fetch_news` from a mandatory LangGraph graph node into an optional tool that the LLM inside `generate_topics` can call at its own discretion. This lets the model decide whether real-time news search is needed based on the context provided, rather than always incurring a network call.

## Section 1: Graph Structure

**Before:**
```
START → fetch_news → generate_topics → human_select_topic → ...
```

**After:**
```
START → generate_topics → human_select_topic → ...
```

### File changes

| File | Action |
|---|---|
| `ai_service/graph/nodes/fetch_news_node.py` | Delete |
| `ai_service/graph/builder.py` | Remove `fetch_news` node registration and its two edges; add `START → generate_topics` direct edge |
| `ai_service/graph/nodes/__init__.py` | Remove `fetch_news` export |

`AgentState.search_results` is **retained** — the `generate_topics` node writes it after execution to record which results the LLM actually used (empty list when the LLM chose not to search). This preserves observability without requiring state schema changes.

## Section 2: Tool Definition & LLMClient

### Tool constant (`llm_client.py`)

```python
_SEARCH_NEWS_TOOL = {
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

### `LLMClient.generate_topics` rewrite

- **New signature:** `generate_topics(self, context: str, search_fn: Callable | None = None) -> tuple[list[str], list[dict]]`
- **API switch:** `responses.create` → `chat.completions.create` (standard tool-calling interface; Volcano Ark supports both)
- **Loop (max 2 iterations):** call LLM with `tools=[_SEARCH_NEWS_TOOL]` + `tool_choice="auto"` → if `tool_calls`: execute `search_fn(query)`, append `role=tool` message, continue → if `content`: parse topics, return. If the loop exhausts without `content` (edge case), return `([], used_results)` as fallback (same graceful-degradation pattern as the old `fetch_news` node).
- **Degraded mode:** when `search_fn=None`, no tool definition is attached (preserves testability without mocking search)
- **Token accounting:** `chat.completions` usage fields are `usage.prompt_tokens` / `completion_tokens`; still routed through `record_token_usage`

## Section 3: Prompt Update (`topic_prompts.yaml`)

```yaml
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

**Key change:** `{search_context}` placeholder removed. Search results are now delivered via the tool call message history, not injected into the template. The template has a single `{context}` variable.

## Section 4: `topic_node.py`

```python
@track_node("generate_topics")
async def generate_topics(state: AgentState) -> dict:
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
```

- `get_web_search()` injected as `search_fn` so the LLM layer remains decoupled from the search singleton
- Return value unpacked to `(topics, search_results)` tuple
- `search_results` written to state: non-empty when LLM called the tool, `[]` when it didn't

## Data Flow

```
generate_topics node
  │
  ├─ llm.generate_topics(context, search_fn)
  │     │
  │     ├─ [Iteration 1] chat.completions.create(messages, tools)
  │     │     └─ LLM decides: call search_news(query)?
  │     │           ├─ YES → search_fn(query) → append tool result → Iteration 2
  │     │           └─ NO  → parse content → return (topics, [])
  │     │
  │     └─ [Iteration 2, if tool was called]
  │           chat.completions.create(messages + tool result)
  │           └─ parse content → return (topics, search_results)
  │
  └─ write {topics, search_results, status} to AgentState
```

## Out of Scope

- Changes to any node other than `generate_topics` and `fetch_news`
- Changes to `AgentState` field names or types
- Frontend / backend API changes
- Existing tests for nodes other than `fetch_news` and `generate_topics`
