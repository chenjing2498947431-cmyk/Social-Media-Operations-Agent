# 设计文档：MCP 联网搜索驱动的选题生成

**日期**：2026-05-27  
**状态**：已确认  
**作者**：Claude Sonnet 4.6

---

## 1. 背景与目标

### 现状问题

当前 `generate_topics`（Node A）完全依赖用户手动输入的 `context` 字符串（如"美联储议息，A股震荡"），由 LLM 直接据此生成 5 个候选选题。这导致：

- 选题脱离当天真实热点，时效性差
- 用户需要自己了解当天新闻才能写出有价值的 context
- `web_search.py` 仅为占位 mock，从未被调用

### 目标

在 `generate_topics` 节点**之前**插入 `fetch_news` 节点，通过 MCP 联网搜索获取当日真实金融热点，将搜索结果与用户输入的 context 一起喂给 LLM，从而生成更具时效性和相关性的选题。

---

## 2. 需求确认

| 维度 | 决策 |
|---|---|
| 搜索触发方式 | 自动搜索：系统将用户输入的 `context` 作为搜索词 |
| 搜索次数 | 每次工作流启动执行 1 次宽泛搜索 |
| 搜索结果处理 | 直接拼入 LLM prompt，不做二次压缩 |
| `context` 字段 | 保持必填，用户必须输入（同时作为搜索词 + 补充背景） |
| MCP 具体实现 | 待用户确认后填入 `web_search.py` |

---

## 3. 架构变化

### 工作流图

```
# 改动前
START → generate_topics → human_select_topic → generate_article → ...

# 改动后
START → fetch_news（新）→ generate_topics（改）→ human_select_topic → generate_article → ...
```

### 数据流

```
用户创建任务（必填 context，如"美联储加息预期"）
    ↓
[fetch_news Node]
  用 state.context 作为搜索词
  调用 MCP 搜索 → 返回 top_k=8 条结果
  写入 state.search_results = [{"title", "snippet", "url"}, ...]
  失败时写入空列表，节点不抛错（降级）
    ↓
[generate_topics Node]（改）
  读取 state.search_results → 格式化为搜索摘要文本
  读取 state.context → 作为补充背景
  拼接进 prompt → LLM → 生成 5 个候选选题
    ↓
[human_select_topic Node]（不变）
  interrupt() 等待人工选题
    ↓
... 后续节点完全不变 ...
```

---

## 4. 各模块详细设计

### 4.1 `AgentState` 新增字段

**文件**：`ai_service/graph/state.py`

```python
class AgentState(TypedDict, total=False):
    context: str
    search_results: list[dict]   # 新增：MCP 搜索结果列表
    topics: list[str]
    selected_topic: Optional[str]
    # ... 其余字段不变
```

`search_results` 每条结构：
```python
{"title": str, "snippet": str, "url": str}
```

### 4.2 `web_search.py` — MCP 接入点

**文件**：`ai_service/tools/web_search.py`

接口约定（用户提供 MCP 后在此处实现）：

```python
class WebSearchTool:
    async def search(self, query: str, top_k: int = 8) -> list[dict]:
        """
        调用 MCP 搜索工具。

        入参：
            query: 搜索词（来自 state.context）
            top_k: 返回结果数量上限

        返回：
            [{"title": str, "snippet": str, "url": str}, ...]
            失败时返回 []，不抛出异常

        待实现：用户确认 MCP 后，在此处接入具体实现。
        """
        raise NotImplementedError("待接入 MCP")
```

**设计原则**：所有 MCP 相关代码**收口在此一处**，其他模块只调用 `get_web_search().search()`。

### 4.3 新建 `fetch_news_node.py`

**文件**：`ai_service/graph/nodes/fetch_news_node.py`（新建）

```python
"""Node 0：联网搜索金融热点，结果存入 state.search_results。"""
from __future__ import annotations
import logging
from ai_service.core.metrics import track_node
from ai_service.graph.state import AgentState
from ai_service.tools.web_search import get_web_search

logger = logging.getLogger(__name__)

@track_node("fetch_news")
async def fetch_news(state: AgentState) -> dict:
    """
    以 state.context 为搜索词联网搜索，将结果写入 state.search_results。

    - 搜索成功：search_results = [{"title", "snippet", "url"}, ...]
    - 搜索失败（网络异常等）：search_results = []，节点不抛错，generate_topics 降级处理
    """
    query = state["context"]
    tool = get_web_search()
    try:
        results = await tool.search(query, top_k=8)
    except Exception as exc:
        logger.warning("fetch_news 搜索失败，降级为空结果: %s", exc)
        results = []
    return {"search_results": results, "status": "running"}
```

**降级策略**：搜索失败时 `search_results=[]`，`generate_topics` 检测到空列表后 prompt 中该区块填写 `"（搜索暂不可用，仅凭背景信息生成）"`，保证工作流不中断。

### 4.4 `topic_node.py` 改动

**文件**：`ai_service/graph/nodes/topic_node.py`

```python
@track_node("generate_topics")
async def generate_topics(state: AgentState) -> dict:
    llm = get_llm_client()
    topics = await llm.generate_topics(
        context=state.get("context", ""),
        search_results=state.get("search_results", []),  # 新增
    )
    return {"topics": topics, "status": "awaiting_topic"}
```

### 4.5 `llm_client.py` — `generate_topics` 方法签名变更

**文件**：`ai_service/tools/llm_client.py`

```python
async def generate_topics(
    self,
    context: str,
    search_results: list[dict] | None = None,
) -> list[str]:
    """将 search_results 格式化为文本后，连同 context 一起填入 prompt。"""
    search_context = _format_search_results(search_results or [])
    text = await self._complete(
        "topic_generator",
        context=context,
        search_context=search_context,
    )
    return _parse_json_array(text)


def _format_search_results(results: list[dict]) -> str:
    """将搜索结果列表格式化为 prompt 可读文本。"""
    if not results:
        return "（搜索暂不可用，仅凭背景信息生成）"
    lines = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "")
        snippet = r.get("snippet", "")
        url = r.get("url", "")
        line = f"{i}. {title}"
        if snippet:
            line += f"\n   {snippet}"
        if url:
            line += f"\n   来源：{url}"
        lines.append(line)
    return "\n".join(lines)
```

### 4.6 `topic_prompts.yaml` 新模板

**文件**：`ai_service/prompts/topic_prompts.yaml`

```yaml
topic_generator:
  system: |
    你是一位资深的金融自媒体主编，擅长基于当日热点产出兼具流量与专业度的选题。
    请输出 5 个备选选题，每个选题不超过 30 字，避免标题党，但要具备话题性。
  user_template: |
    【今日联网搜索热点】
    {search_context}

    【补充背景（运营备注）】
    {context}

    请综合以上信息，输出 5 个备选选题的 JSON 数组，例如：
    ["选题 A", "选题 B", "选题 C", "选题 D", "选题 E"]
```

### 4.7 `builder.py` 图结构调整

**文件**：`ai_service/graph/builder.py`

```python
from ai_service.graph.nodes import (
    fetch_news,           # 新增导入
    generate_topics,
    human_select_topic,
    # ...
)

def build_graph():
    builder = StateGraph(AgentState)
    builder.add_node("fetch_news", fetch_news)        # 新增节点
    builder.add_node("generate_topics", generate_topics)
    # ... 其余节点不变

    builder.add_edge(START, "fetch_news")             # 改：START → fetch_news
    builder.add_edge("fetch_news", "generate_topics") # 新增
    builder.add_edge("generate_topics", "human_select_topic")
    # ... 其余边不变
```

### 4.8 Schemas — 无需改动

`context` 保持必填，`WorkflowStartRequest` 不变。

---

## 5. 错误处理策略

| 场景 | 处理方式 |
|---|---|
| MCP 搜索超时/异常 | `fetch_news` 捕获异常，返回 `search_results=[]`，工作流继续 |
| 搜索结果为空列表 | prompt 中显示"搜索暂不可用"，LLM 仅凭 context 生成选题 |
| MCP 未实现（`NotImplementedError`）| 同上，降级处理 |
| LLM 生成失败 | 已有 `track_node` 兜底，行为不变 |

---

## 6. 待确认事项

- [ ] 用户提供具体 MCP 名称/配置后，实现 `web_search.py` 中的 `search()` 方法
- [ ] 确认 MCP 返回的数据结构，按需调整 `_format_search_results()` 的字段映射

---

## 7. 不在本次范围内

- 前端展示搜索结果来源（可作后续迭代）
- 多次定向搜索
- 搜索结果的二次 LLM 压缩
- 鉴权/限流

---

## 8. 涉及文件汇总

| 文件 | 改动类型 | 说明 |
|---|---|---|
| `ai_service/graph/state.py` | 修改 | 新增 `search_results` 字段 |
| `ai_service/tools/web_search.py` | 修改 | 替换 mock，定义 MCP 接入接口 |
| `ai_service/graph/nodes/fetch_news_node.py` | **新建** | `fetch_news` 节点实现 |
| `ai_service/graph/nodes/__init__.py` | 修改 | 导出 `fetch_news` |
| `ai_service/graph/nodes/topic_node.py` | 修改 | 传入 `search_results` 参数 |
| `ai_service/tools/llm_client.py` | 修改 | `generate_topics` 接受 `search_results`，新增格式化函数 |
| `ai_service/graph/builder.py` | 修改 | 插入 `fetch_news` 节点和边 |
| `ai_service/prompts/topic_prompts.yaml` | 修改 | 新增 `search_context` 占位符 |
