# MCP 联网搜索驱动选题生成 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 LangGraph 工作流中新增 `fetch_news` 节点，通过 Brave Search MCP Server（HTTP 模式，port 8200）搜索当日金融热点，将结果注入 `generate_topics` 节点的 LLM prompt，使选题具备真实时效性。

**Architecture:** 在 `generate_topics` 前插入 `fetch_news` 节点（`START → fetch_news → generate_topics → ...`）。`fetch_news` 调用 `WebSearchTool.search()`，后者通过标准 MCP HTTP 协议（initialize → notifications/initialized → tools/call）与本地 Brave Search MCP Server 通信，返回新闻列表写入 `state.search_results`。`generate_topics` 读取该字段，格式化后拼入 prompt。MCP 服务器需单独启动，ai_service 通过 `BRAVE_MCP_URL` 环境变量定位它。

**Tech Stack:** Python 3.13 · httpx（已在 requirements.txt）· LangGraph · pytest + pytest-asyncio（测试）· Brave Search MCP Server（Node.js，本地 HTTP 模式 port 8200）

---

## 文件清单

| 操作 | 路径 | 说明 |
|---|---|---|
| 修改 | `ai_service/graph/state.py` | 新增 `search_results` 字段 |
| 修改 | `ai_service/core/config.py` | 新增 `brave_mcp_url` 配置项 |
| 修改 | `ai_service/core/metrics.py` | `NODE_LABELS` 增加 `fetch_news` 标签 |
| 修改 | `ai_service/tools/web_search.py` | 替换 mock → 真实 MCP HTTP 客户端 |
| 新建 | `ai_service/graph/nodes/fetch_news_node.py` | `fetch_news` 节点实现 |
| 修改 | `ai_service/graph/nodes/__init__.py` | 导出 `fetch_news` |
| 修改 | `ai_service/graph/nodes/topic_node.py` | 传入 `search_results` 给 LLM |
| 修改 | `ai_service/tools/llm_client.py` | `generate_topics` 接受 `search_results`，新增 `_format_search_results` |
| 修改 | `ai_service/prompts/topic_prompts.yaml` | 新增 `{search_context}` 占位符 |
| 修改 | `ai_service/graph/builder.py` | 插入 `fetch_news` 节点和边 |
| 修改 | `.env.example` | 新增 `BRAVE_MCP_URL` 说明 |
| 修改 | `.env` | 新增 `BRAVE_MCP_URL=http://localhost:8200/mcp` |
| 新建 | `tests/__init__.py` | 测试包 |
| 新建 | `tests/test_web_search.py` | WebSearchTool 单元测试 |
| 新建 | `tests/test_fetch_news_node.py` | fetch_news 节点单元测试 |
| 新建 | `tests/test_topic_node.py` | generate_topics 节点单元测试 |
| 新建 | `tests/test_llm_client_topics.py` | generate_topics + _format_search_results 单元测试 |
| 删除/替换 | `scripts/test_mcp.py` | 临时测试脚本，任务完成后可删除 |

---

## Task 1: 安装测试依赖 + 创建测试包

**Files:**
- Create: `tests/__init__.py`

- [ ] **Step 1: 安装 pytest 和 pytest-asyncio**

```powershell
# 在 media conda 环境中安装
D:\Anaconda3\envs\media\Scripts\pip.exe install pytest pytest-asyncio -q
```

验证：
```powershell
D:\Anaconda3\envs\media\python.exe -m pytest --version
```
期望输出类似 `pytest 8.x.x`

- [ ] **Step 2: 创建测试包**

新建 `tests/__init__.py`（空文件）：
```python
```

- [ ] **Step 3: 新建 `pytest.ini`（项目根目录）**

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```

- [ ] **Step 4: 验证 pytest 可发现测试目录**

```powershell
cd d:\Code\Media_Agent\financial_agent_project
D:\Anaconda3\envs\media\python.exe -m pytest tests/ --collect-only
```
期望：`no tests ran`（目录可发现，无报错）

---

## Task 2: 更新 `AgentState` + 新增 MCP 配置

**Files:**
- Modify: `ai_service/graph/state.py`
- Modify: `ai_service/core/config.py`
- Modify: `.env.example`
- Modify: `.env`

- [ ] **Step 1: 编写 state 字段测试**

新建 `tests/test_state.py`：
```python
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
```

- [ ] **Step 2: 运行测试，确认失败**

```powershell
cd d:\Code\Media_Agent\financial_agent_project
D:\Anaconda3\envs\media\python.exe -m pytest tests/test_state.py -v
```
期望：`FAILED` — `KeyError: 'search_results'` 或类型检查错误

- [ ] **Step 3: 修改 `ai_service/graph/state.py`，新增 `search_results` 字段**

将文件改为：
```python
"""LangGraph 全局状态定义。"""
from __future__ import annotations

from operator import add
from typing import Annotated, Optional, TypedDict


class AgentState(TypedDict, total=False):
    # 输入背景：每日金融热点 / 用户偏好
    context: str

    # 联网搜索结果（fetch_news 节点写入）
    search_results: list[dict]

    # 选题环节
    topics: list[str]
    selected_topic: Optional[str]

    # 写作 / 审核环节
    draft_article: Optional[str]
    human_feedback: Optional[str]
    revision_round: int  # 已经重写了几轮

    # 图片环节
    image_prompts: list[str]
    generated_images: list[str]

    # 工作流状态
    status: str  # awaiting_topic / awaiting_review / running / completed / failed

    # 条件边专用字段：上一次人工审核的决定 (approve / reject)
    _last_decision: Optional[str]

    # 运行指标：每个 AI 计算节点执行后追加一条
    node_metrics: Annotated[list[dict], add]
```

- [ ] **Step 4: 运行测试，确认通过**

```powershell
D:\Anaconda3\envs\media\python.exe -m pytest tests/test_state.py -v
```
期望：`2 passed`

- [ ] **Step 5: 修改 `ai_service/core/config.py`，新增 `brave_mcp_url`**

将文件改为：
```python
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class AIServiceSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ai_service_host: str = "0.0.0.0"
    ai_service_port: int = 8100

    langgraph_checkpoint_dsn: Optional[str] = None

    # 火山方舟 (Ark) 大模型配置，OpenAI 兼容接口
    ark_api_key: Optional[str] = None
    ark_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    ark_model: str = "ep-20260516141907-ggmpz"
    # 文生图模型（doubao-seedream）
    ark_image_model: str = "doubao-seedream-4-5-251128"

    # Brave Search MCP Server（本地 HTTP 模式）
    brave_mcp_url: str = "http://localhost:8200/mcp"


@lru_cache
def get_settings() -> AIServiceSettings:
    return AIServiceSettings()
```

- [ ] **Step 6: 在 `.env` 末尾追加 MCP 配置**

在 `.env` 文件末尾添加：
```ini
# Brave Search MCP Server
BRAVE_MCP_URL=http://localhost:8200/mcp
```

- [ ] **Step 7: 在 `.env.example` 末尾追加 MCP 配置说明**

在 `.env.example` 文件末尾添加：
```ini
# ============================================================
# Brave Search MCP Server（联网搜索，用于选题生成）
# ============================================================
# 启动命令：BRAVE_API_KEY=xxx npx -y @brave/brave-search-mcp-server --transport http --port 8200
# 申请 API Key：https://api-dashboard.search.brave.com
BRAVE_MCP_URL=http://localhost:8200/mcp
```

- [ ] **Step 8: Commit**

```powershell
cd d:\Code\Media_Agent\financial_agent_project
git add ai_service/graph/state.py ai_service/core/config.py .env.example tests/
git commit -m "feat: add search_results to AgentState and brave_mcp_url config"
```

---

## Task 3: 实现 `WebSearchTool`（真实 MCP HTTP 客户端）

**Files:**
- Modify: `ai_service/tools/web_search.py`
- Create: `tests/test_web_search.py`

- [ ] **Step 1: 编写 WebSearchTool 单元测试**

新建 `tests/test_web_search.py`：
```python
"""WebSearchTool 单元测试：mock httpx，验证 MCP 协议流程和结果解析。"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_service.tools.web_search import WebSearchTool


def _sse(payload: dict) -> str:
    """构造 SSE 响应文本。"""
    return f"event: message\ndata: {json.dumps(payload)}\n\n"


def _make_mock_response(status: int, text: str, headers: dict | None = None) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.text = text
    r.headers = headers or {}
    r.raise_for_status = MagicMock()
    return r


@pytest.mark.asyncio
async def test_search_returns_parsed_results():
    """search() 成功时返回解析好的 list[dict]。"""
    init_payload = {"result": {"protocolVersion": "2024-11-05", "serverInfo": {}}}
    news_items = [
        {"url": "https://a.com", "title": "美联储加息", "description": "加息25bp", "age": "1 hour ago"},
        {"url": "https://b.com", "title": "A股下跌", "description": "沪指跌0.5%", "age": "2 hours ago"},
    ]
    search_payload = {
        "result": {
            "content": [
                {"type": "text", "text": json.dumps(item)} for item in news_items
            ]
        }
    }

    mock_init_resp = _make_mock_response(200, _sse(init_payload), {"mcp-session-id": "sess-123"})
    mock_notify_resp = _make_mock_response(202, "")
    mock_search_resp = _make_mock_response(200, _sse(search_payload))

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=[mock_init_resp, mock_notify_resp, mock_search_resp])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    tool = WebSearchTool(mcp_url="http://localhost:8200/mcp")
    with patch("ai_service.tools.web_search.httpx.AsyncClient", return_value=mock_client):
        results = await tool.search("美联储", top_k=5)

    assert len(results) == 2
    assert results[0]["title"] == "美联储加息"
    assert results[0]["snippet"] == "加息25bp"
    assert results[0]["url"] == "https://a.com"
    assert results[1]["title"] == "A股下跌"


@pytest.mark.asyncio
async def test_search_passes_session_id_in_subsequent_requests():
    """initialize 返回 mcp-session-id 后，后续请求必须携带该 header。"""
    init_payload = {"result": {}}
    search_payload = {"result": {"content": []}}

    mock_init_resp = _make_mock_response(200, _sse(init_payload), {"mcp-session-id": "my-session-id"})
    mock_notify_resp = _make_mock_response(202, "")
    mock_search_resp = _make_mock_response(200, _sse(search_payload))

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=[mock_init_resp, mock_notify_resp, mock_search_resp])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    tool = WebSearchTool(mcp_url="http://localhost:8200/mcp")
    with patch("ai_service.tools.web_search.httpx.AsyncClient", return_value=mock_client):
        await tool.search("测试", top_k=3)

    # notifications/initialized call (index 1) should have session header
    notify_call_kwargs = mock_client.post.call_args_list[1][1]
    assert notify_call_kwargs["headers"].get("mcp-session-id") == "my-session-id"

    # tools/call (index 2) should also have session header
    search_call_kwargs = mock_client.post.call_args_list[2][1]
    assert search_call_kwargs["headers"].get("mcp-session-id") == "my-session-id"


@pytest.mark.asyncio
async def test_search_respects_top_k():
    """search() 返回结果数量不超过 top_k。"""
    news_items = [
        {"url": f"https://{i}.com", "title": f"新闻{i}", "description": f"摘要{i}", "age": "1h"}
        for i in range(10)
    ]
    search_payload = {
        "result": {"content": [{"type": "text", "text": json.dumps(item)} for item in news_items]}
    }
    mock_init_resp = _make_mock_response(200, _sse({"result": {}}), {"mcp-session-id": "s"})
    mock_notify_resp = _make_mock_response(202, "")
    mock_search_resp = _make_mock_response(200, _sse(search_payload))

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=[mock_init_resp, mock_notify_resp, mock_search_resp])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    tool = WebSearchTool(mcp_url="http://localhost:8200/mcp")
    with patch("ai_service.tools.web_search.httpx.AsyncClient", return_value=mock_client):
        results = await tool.search("测试", top_k=3)

    assert len(results) == 3


@pytest.mark.asyncio
async def test_search_returns_empty_on_http_error():
    """HTTP 异常时返回空列表，不抛出异常。"""
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=Exception("Connection refused"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    tool = WebSearchTool(mcp_url="http://localhost:8200/mcp")
    with patch("ai_service.tools.web_search.httpx.AsyncClient", return_value=mock_client):
        results = await tool.search("测试", top_k=5)

    assert results == []
```

- [ ] **Step 2: 运行测试，确认失败**

```powershell
cd d:\Code\Media_Agent\financial_agent_project
D:\Anaconda3\envs\media\python.exe -m pytest tests/test_web_search.py -v
```
期望：`ImportError` 或 `4 failed`（WebSearchTool 没有 `mcp_url` 参数）

- [ ] **Step 3: 实现 `ai_service/tools/web_search.py`**

将文件整体替换为：
```python
"""Brave Search MCP Server 客户端。

通过标准 MCP HTTP 协议（initialize → notifications/initialized → tools/call）
调用本地 brave-search-mcp-server，返回新闻列表。

启动 MCP Server：
    BRAVE_API_KEY=<key> npx -y @brave/brave-search-mcp-server --transport http --port 8200

环境变量：
    BRAVE_MCP_URL  MCP Server 的 /mcp 端点（默认 http://localhost:8200/mcp）
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from ai_service.core.config import get_settings

logger = logging.getLogger(__name__)

_MCP_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


class WebSearchTool:
    """通过 MCP HTTP 协议调用 Brave Search 的新闻搜索工具。"""

    def __init__(self, mcp_url: str | None = None) -> None:
        self._mcp_url = mcp_url or get_settings().brave_mcp_url

    async def search(self, query: str, top_k: int = 8) -> list[dict[str, Any]]:
        """搜索新闻，返回 [{"title": str, "snippet": str, "url": str}, ...]。

        失败时返回空列表，不抛出异常（调用方降级处理）。
        """
        try:
            return await self._do_search(query, top_k)
        except Exception as exc:
            logger.warning("WebSearchTool.search 失败，返回空结果: %s", exc)
            return []

    async def _do_search(self, query: str, top_k: int) -> list[dict[str, Any]]:
        """实际执行 MCP 三步协议。"""
        async with httpx.AsyncClient(timeout=15) as client:
            # Step 1: initialize
            init_resp = await client.post(
                self._mcp_url,
                headers=_MCP_HEADERS,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "ai-service", "version": "1.0"},
                    },
                },
            )
            init_resp.raise_for_status()
            session_id = init_resp.headers.get("mcp-session-id")

            # 后续请求携带 session id
            req_headers = dict(_MCP_HEADERS)
            if session_id:
                req_headers["mcp-session-id"] = session_id

            # Step 2: notifications/initialized
            await client.post(
                self._mcp_url,
                headers=req_headers,
                json={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            )

            # Step 3: tools/call brave_news_search
            search_resp = await client.post(
                self._mcp_url,
                headers=req_headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "brave_news_search",
                        "arguments": {"query": query, "count": top_k, "freshness": "pd"},
                    },
                },
            )
            search_resp.raise_for_status()

        data = _parse_sse(search_resp.text)
        if not data:
            return []
        return _extract_news(data, top_k)


def _parse_sse(text: str) -> dict[str, Any] | None:
    """从 SSE 格式响应文本中提取并解析第一条 data: 行。"""
    for line in text.splitlines():
        if line.startswith("data:"):
            try:
                return json.loads(line[5:].strip())
            except json.JSONDecodeError:
                pass
    return None


def _extract_news(data: dict[str, Any], top_k: int) -> list[dict[str, Any]]:
    """从 MCP tools/call 响应中提取新闻列表。

    MCP 响应结构：
        {"result": {"content": [{"type": "text", "text": "{...json...}"}, ...]}}
    每条 text 是一个 JSON 字符串，字段包含 title / description / url。
    """
    content = data.get("result", {}).get("content", [])
    results: list[dict[str, Any]] = []
    for item in content:
        if item.get("type") != "text":
            continue
        try:
            news = json.loads(item["text"])
        except (json.JSONDecodeError, KeyError):
            continue
        results.append({
            "title": news.get("title", ""),
            "snippet": news.get("description", ""),
            "url": news.get("url", ""),
        })
        if len(results) >= top_k:
            break
    return results


_search: WebSearchTool | None = None


def get_web_search() -> WebSearchTool:
    global _search
    if _search is None:
        _search = WebSearchTool()
    return _search


def reset_web_search() -> None:
    """测试用：清掉单例。"""
    global _search
    _search = None
```

- [ ] **Step 4: 运行测试，确认通过**

```powershell
D:\Anaconda3\envs\media\python.exe -m pytest tests/test_web_search.py -v
```
期望：`4 passed`

- [ ] **Step 5: Commit**

```powershell
git add ai_service/tools/web_search.py tests/test_web_search.py
git commit -m "feat: implement WebSearchTool with Brave Search MCP HTTP client"
```

---

## Task 4: 更新 `metrics.py`，新建 `fetch_news_node.py`

**Files:**
- Modify: `ai_service/core/metrics.py`
- Create: `ai_service/graph/nodes/fetch_news_node.py`
- Create: `tests/test_fetch_news_node.py`

- [ ] **Step 1: 编写 fetch_news 节点测试**

新建 `tests/test_fetch_news_node.py`：
```python
"""fetch_news 节点单元测试。"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from ai_service.graph.nodes.fetch_news_node import fetch_news


@pytest.mark.asyncio
async def test_fetch_news_writes_results_to_state():
    """搜索成功时，search_results 写入返回 dict。"""
    mock_results = [
        {"title": "美联储加息", "snippet": "加息25bp", "url": "https://a.com"},
        {"title": "A股下跌", "snippet": "沪指跌0.5%", "url": "https://b.com"},
    ]
    state = {"context": "美联储加息预期", "status": "running", "node_metrics": []}

    with patch("ai_service.graph.nodes.fetch_news_node.get_web_search") as mock_get:
        mock_tool = AsyncMock()
        mock_tool.search = AsyncMock(return_value=mock_results)
        mock_get.return_value = mock_tool

        result = await fetch_news(state)

    assert result["search_results"] == mock_results
    assert result["status"] == "running"
    mock_tool.search.assert_called_once_with("美联储加息预期", top_k=8)


@pytest.mark.asyncio
async def test_fetch_news_uses_context_as_query():
    """确认 search() 的 query 参数来自 state['context']。"""
    state = {"context": "黄金创新高 通胀数据", "status": "running", "node_metrics": []}

    with patch("ai_service.graph.nodes.fetch_news_node.get_web_search") as mock_get:
        mock_tool = AsyncMock()
        mock_tool.search = AsyncMock(return_value=[])
        mock_get.return_value = mock_tool

        await fetch_news(state)

    mock_tool.search.assert_called_once_with("黄金创新高 通胀数据", top_k=8)


@pytest.mark.asyncio
async def test_fetch_news_degrades_gracefully_on_search_failure():
    """搜索异常时，search_results 为空列表，节点不抛出异常。"""
    state = {"context": "测试", "status": "running", "node_metrics": []}

    with patch("ai_service.graph.nodes.fetch_news_node.get_web_search") as mock_get:
        mock_tool = AsyncMock()
        mock_tool.search = AsyncMock(side_effect=Exception("网络超时"))
        mock_get.return_value = mock_tool

        # WebSearchTool.search 内部已 catch，此处不应抛出
        result = await fetch_news(state)

    assert result["search_results"] == []
```

- [ ] **Step 2: 运行测试，确认失败**

```powershell
D:\Anaconda3\envs\media\python.exe -m pytest tests/test_fetch_news_node.py -v
```
期望：`ImportError`（模块不存在）

- [ ] **Step 3: 在 `metrics.py` 的 `NODE_LABELS` 中添加 `fetch_news`**

在 `ai_service/core/metrics.py` 的 `NODE_LABELS` 字典中添加一行：
```python
NODE_LABELS: dict[str, str] = {
    "fetch_news": "新闻搜索",          # ← 新增这一行
    "generate_topics": "选题生成",
    "generate_article": "文案撰写",
    "revise_article": "文案改写",
    "extract_image_content": "配图文案提炼",
    "generate_images": "配图生成",
}
```

- [ ] **Step 4: 新建 `ai_service/graph/nodes/fetch_news_node.py`**

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
    """以 state.context 为搜索词联网搜索，将结果写入 state.search_results。

    - 搜索成功：search_results = [{"title", "snippet", "url"}, ...]
    - 搜索失败：search_results = []，节点不抛错，generate_topics 降级处理
    """
    query = state["context"]
    tool = get_web_search()
    results = await tool.search(query, top_k=8)
    return {"search_results": results, "status": "running"}
```

> 注意：`WebSearchTool.search()` 内部已 catch 所有异常并返回 `[]`，所以 `fetch_news` 无需额外 try/except。

- [ ] **Step 5: 运行测试，确认通过**

```powershell
D:\Anaconda3\envs\media\python.exe -m pytest tests/test_fetch_news_node.py -v
```
期望：`3 passed`

- [ ] **Step 6: Commit**

```powershell
git add ai_service/core/metrics.py ai_service/graph/nodes/fetch_news_node.py tests/test_fetch_news_node.py
git commit -m "feat: add fetch_news node with MCP news search"
```

---

## Task 5: 更新 `llm_client.py`（`generate_topics` + `_format_search_results`）

**Files:**
- Modify: `ai_service/tools/llm_client.py`
- Create: `tests/test_llm_client_topics.py`

- [ ] **Step 1: 编写 llm_client 测试**

新建 `tests/test_llm_client_topics.py`：
```python
"""测试 generate_topics 方法和 _format_search_results 函数。"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from ai_service.tools.llm_client import LLMClient, _format_search_results


# ---------- _format_search_results ----------

def test_format_empty_results_returns_fallback():
    result = _format_search_results([])
    assert result == "（搜索暂不可用，仅凭背景信息生成）"


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


def test_format_results_handles_missing_fields():
    """snippet 或 url 缺失时不应抛出 KeyError。"""
    results = [{"title": "仅标题"}]
    text = _format_search_results(results)
    assert "1. 仅标题" in text


# ---------- generate_topics ----------

@pytest.mark.asyncio
async def test_generate_topics_passes_search_context_to_complete():
    """generate_topics 把格式化后的 search_context 传给 _complete。"""
    search_results = [
        {"title": "美联储加息", "snippet": "加息25bp", "url": "https://a.com"},
    ]
    client = LLMClient()

    with patch.object(client, "_complete", new_callable=AsyncMock) as mock_complete:
        mock_complete.return_value = '["选题A", "选题B", "选题C", "选题D", "选题E"]'
        topics = await client.generate_topics(
            context="美联储议息",
            search_results=search_results,
        )

    mock_complete.assert_called_once()
    call_kwargs = mock_complete.call_args[1]
    assert "search_context" in call_kwargs
    assert "美联储加息" in call_kwargs["search_context"]
    assert call_kwargs["context"] == "美联储议息"
    assert topics == ["选题A", "选题B", "选题C", "选题D", "选题E"]


@pytest.mark.asyncio
async def test_generate_topics_with_empty_search_results():
    """search_results 为空时，search_context 为降级文本，不报错。"""
    client = LLMClient()

    with patch.object(client, "_complete", new_callable=AsyncMock) as mock_complete:
        mock_complete.return_value = '["选题A", "选题B"]'
        topics = await client.generate_topics(context="美联储", search_results=[])

    call_kwargs = mock_complete.call_args[1]
    assert "搜索暂不可用" in call_kwargs["search_context"]
    assert topics == ["选题A", "选题B"]


@pytest.mark.asyncio
async def test_generate_topics_without_search_results_param():
    """search_results 默认为 None 时，降级处理，不报错。"""
    client = LLMClient()

    with patch.object(client, "_complete", new_callable=AsyncMock) as mock_complete:
        mock_complete.return_value = '["选题A"]'
        topics = await client.generate_topics(context="美联储")

    assert topics == ["选题A"]
```

- [ ] **Step 2: 运行测试，确认失败**

```powershell
D:\Anaconda3\envs\media\python.exe -m pytest tests/test_llm_client_topics.py -v
```
期望：`FAILED` — `_format_search_results` 未导出，`generate_topics` 签名不匹配

- [ ] **Step 3: 修改 `ai_service/tools/llm_client.py`**

在文件顶部（`_parse_json_array` 函数之后，`LLMClient` 类之前）添加 `_format_search_results` 函数：

```python
def _format_search_results(results: list[dict]) -> str:
    """将 MCP 搜索结果列表格式化为 prompt 可读文本。

    每条格式：
        N. 标题
           摘要
           来源：URL
    """
    if not results:
        return "（搜索暂不可用，仅凭背景信息生成）"
    lines: list[str] = []
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

将 `LLMClient.generate_topics` 方法替换为：

```python
async def generate_topics(
    self,
    context: str,
    search_results: list[dict] | None = None,
) -> list[str]:
    """根据搜索结果和背景信息生成候选选题列表。"""
    search_context = _format_search_results(search_results or [])
    text = await self._complete(
        "topic_generator",
        context=context,
        search_context=search_context,
    )
    return _parse_json_array(text)
```

在 `__all__` 中新增 `_format_search_results`（供测试直接导入）：

```python
__all__: list[Any] = [
    "LLMClient",
    "get_llm_client",
    "reload_llm_client",
    "_format_search_results",
]
```

- [ ] **Step 4: 运行测试，确认通过**

```powershell
D:\Anaconda3\envs\media\python.exe -m pytest tests/test_llm_client_topics.py -v
```
期望：`5 passed`

- [ ] **Step 5: Commit**

```powershell
git add ai_service/tools/llm_client.py tests/test_llm_client_topics.py
git commit -m "feat: update generate_topics to accept search_results, add _format_search_results"
```

---

## Task 6: 更新 `topic_prompts.yaml`

**Files:**
- Modify: `ai_service/prompts/topic_prompts.yaml`

- [ ] **Step 1: 替换 prompt 模板**

将 `ai_service/prompts/topic_prompts.yaml` 整体替换为：

```yaml
# 选题生成 Prompt 配置
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

- [ ] **Step 2: 验证模板渲染正常**

```powershell
cd d:\Code\Media_Agent\financial_agent_project
D:\Anaconda3\envs\media\python.exe -c "
from ai_service.prompts import get_prompt
p = get_prompt('topic_generator')
rendered = p['user_template'].format(
    search_context='1. 美联储加息25bp\n   来源：https://a.com',
    context='美联储议息会议'
)
print(rendered)
"
```
期望：打印出包含两个区块的 prompt 文本，无 `KeyError`

- [ ] **Step 3: Commit**

```powershell
git add ai_service/prompts/topic_prompts.yaml
git commit -m "feat: update topic_generator prompt to include search_context"
```

---

## Task 7: 更新 `topic_node.py`

**Files:**
- Modify: `ai_service/graph/nodes/topic_node.py`
- Create: `tests/test_topic_node.py`

- [ ] **Step 1: 编写 topic_node 测试**

新建 `tests/test_topic_node.py`：
```python
"""generate_topics 节点单元测试。"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from ai_service.graph.nodes.topic_node import generate_topics


@pytest.mark.asyncio
async def test_generate_topics_passes_search_results_from_state():
    """节点从 state.search_results 读取数据并传给 LLM。"""
    search_results = [
        {"title": "美联储加息", "snippet": "加息25bp", "url": "https://a.com"},
    ]
    state = {
        "context": "美联储议息",
        "search_results": search_results,
        "status": "running",
        "node_metrics": [],
    }

    with patch("ai_service.graph.nodes.topic_node.get_llm_client") as mock_get:
        mock_llm = AsyncMock()
        mock_llm.generate_topics = AsyncMock(return_value=["选题A", "选题B", "选题C", "选题D", "选题E"])
        mock_get.return_value = mock_llm

        result = await generate_topics(state)

    mock_llm.generate_topics.assert_called_once_with(
        context="美联储议息",
        search_results=search_results,
    )
    assert result["topics"] == ["选题A", "选题B", "选题C", "选题D", "选题E"]
    assert result["status"] == "awaiting_topic"


@pytest.mark.asyncio
async def test_generate_topics_handles_missing_search_results():
    """state 中没有 search_results 时，传 [] 给 LLM，不报错。"""
    state = {
        "context": "黄金创新高",
        "status": "running",
        "node_metrics": [],
    }

    with patch("ai_service.graph.nodes.topic_node.get_llm_client") as mock_get:
        mock_llm = AsyncMock()
        mock_llm.generate_topics = AsyncMock(return_value=["选题X"])
        mock_get.return_value = mock_llm

        result = await generate_topics(state)

    mock_llm.generate_topics.assert_called_once_with(
        context="黄金创新高",
        search_results=[],
    )
    assert result["topics"] == ["选题X"]
```

- [ ] **Step 2: 运行测试，确认失败**

```powershell
D:\Anaconda3\envs\media\python.exe -m pytest tests/test_topic_node.py -v
```
期望：`FAILED` — `generate_topics` 未传 `search_results` 参数

- [ ] **Step 3: 修改 `ai_service/graph/nodes/topic_node.py`**

将文件整体替换为：
```python
"""Node A & Node B：选题生成 + 人工选题中断。"""
from __future__ import annotations

from langgraph.types import interrupt

from ai_service.core.metrics import track_node
from ai_service.graph.state import AgentState
from ai_service.tools.llm_client import get_llm_client


@track_node("generate_topics")
async def generate_topics(state: AgentState) -> dict:
    """Node A: 结合联网搜索结果和背景信息生成备选选题。"""
    llm = get_llm_client()
    topics = await llm.generate_topics(
        context=state.get("context", ""),
        search_results=state.get("search_results", []),
    )
    return {
        "topics": topics,
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

- [ ] **Step 4: 运行测试，确认通过**

```powershell
D:\Anaconda3\envs\media\python.exe -m pytest tests/test_topic_node.py -v
```
期望：`2 passed`

- [ ] **Step 5: Commit**

```powershell
git add ai_service/graph/nodes/topic_node.py tests/test_topic_node.py
git commit -m "feat: update topic_node to pass search_results to LLM"
```

---

## Task 8: 更新 `builder.py` + `nodes/__init__.py`

**Files:**
- Modify: `ai_service/graph/builder.py`
- Modify: `ai_service/graph/nodes/__init__.py`

- [ ] **Step 1: 修改 `ai_service/graph/nodes/__init__.py`**

将文件整体替换为：
```python
from .fetch_news_node import fetch_news
from .topic_node import generate_topics, human_select_topic
from .writer_node import generate_article
from .critic_node import human_review_article, revise_article
from .image_node import extract_image_content, generate_images

__all__ = [
    "fetch_news",
    "generate_topics",
    "human_select_topic",
    "generate_article",
    "human_review_article",
    "revise_article",
    "extract_image_content",
    "generate_images",
]
```

- [ ] **Step 2: 修改 `ai_service/graph/builder.py`**

将文件整体替换为：
```python
"""LangGraph StateGraph 组装。"""
from __future__ import annotations

from langgraph.graph import StateGraph, START, END

from ai_service.graph.state import AgentState
from ai_service.graph.nodes import (
    fetch_news,
    generate_topics,
    human_select_topic,
    generate_article,
    human_review_article,
    revise_article,
    extract_image_content,
    generate_images,
)
from ai_service.graph.edges import route_after_review
from ai_service.persistence.checkpointer import get_checkpointer


def build_graph():
    builder = StateGraph(AgentState)

    builder.add_node("fetch_news", fetch_news)
    builder.add_node("generate_topics", generate_topics)
    builder.add_node("human_select_topic", human_select_topic)
    builder.add_node("generate_article", generate_article)
    builder.add_node("human_review_article", human_review_article)
    builder.add_node("revise_article", revise_article)
    builder.add_node("extract_image_content", extract_image_content)
    builder.add_node("generate_images", generate_images)

    builder.add_edge(START, "fetch_news")
    builder.add_edge("fetch_news", "generate_topics")
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
    builder.add_edge("generate_images", END)

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

- [ ] **Step 3: 验证图可以正常编译（使用 InMemorySaver，无需 Postgres）**

```powershell
cd d:\Code\Media_Agent\financial_agent_project
D:\Anaconda3\envs\media\python.exe -c "
import os
os.environ.setdefault('ARK_API_KEY', 'test')
from ai_service.graph.builder import build_graph
g = build_graph()
print('节点列表:', list(g.nodes.keys()))
print('图编译成功 ✅')
"
```
期望输出包含：`fetch_news`, `generate_topics`, `human_select_topic` 等节点名，以及 `图编译成功 ✅`

- [ ] **Step 4: 运行全部测试，确认无回归**

```powershell
D:\Anaconda3\envs\media\python.exe -m pytest tests/ -v
```
期望：所有测试通过（12+ passed，0 failed）

- [ ] **Step 5: Commit**

```powershell
git add ai_service/graph/nodes/__init__.py ai_service/graph/builder.py
git commit -m "feat: wire fetch_news node into LangGraph workflow (START -> fetch_news -> generate_topics)"
```

---

## Task 9: 端到端冒烟测试

**Files:**
- Modify: `scripts/test_mcp.py`（更新为正式冒烟测试，或删除）

- [ ] **Step 1: 确认 MCP Server 正在运行**

在**新的终端窗口**中执行（保持运行）：
```powershell
$env:BRAVE_API_KEY="BSAM5u1hM0yiIhf8AG_pNI1XQ-uSU78"
npx -y @brave/brave-search-mcp-server --transport http --port 8200
```
等待看到 `Server is running on http://0.0.0.0:8200/mcp`

- [ ] **Step 2: 测试 WebSearchTool 真实调用**

```powershell
cd d:\Code\Media_Agent\financial_agent_project
D:\Anaconda3\envs\media\python.exe -c "
import asyncio
from ai_service.tools.web_search import WebSearchTool

async def main():
    tool = WebSearchTool()
    results = await tool.search('美联储 A股 金融市场', top_k=3)
    print(f'搜索到 {len(results)} 条结果:')
    for r in results:
        print(f'  - {r[\"title\"][:40]}')
        print(f'    {r[\"url\"]}')

asyncio.run(main())
"
```
期望：打印出 3 条真实新闻标题和 URL

- [ ] **Step 3: 删除临时测试脚本**

```powershell
del d:\Code\Media_Agent\financial_agent_project\scripts\test_mcp.py
```

- [ ] **Step 4: 最终 Commit**

```powershell
git add -A
git commit -m "chore: remove temp test_mcp.py, all tasks complete"
```

---

## 自查清单（Self-Review）

### Spec 覆盖检查
- ✅ `fetch_news` 节点（Task 4）
- ✅ `WebSearchTool` 真实 MCP HTTP 实现（Task 3）
- ✅ `AgentState.search_results` 字段（Task 2）
- ✅ `generate_topics` 接受 `search_results`（Task 5）
- ✅ `topic_prompts.yaml` 新增 `{search_context}`（Task 6）
- ✅ `builder.py` 插入 `fetch_news` 节点（Task 8）
- ✅ `context` 保持必填（无改动）
- ✅ MCP 接入收口在 `web_search.py` 一处（Task 3）
- ✅ 降级策略（搜索失败返回 `[]`，Task 3 Step 3 + Task 4 Step 4）
- ✅ `.env` / `.env.example` 配置（Task 2）

### 类型一致性检查
- `search_results: list[dict]` 在 `AgentState`、`WebSearchTool.search()` 返回值、`generate_topics()` 参数中保持一致 ✅
- `_format_search_results(results: list[dict]) -> str` 签名在 `llm_client.py` 和 `test_llm_client_topics.py` 中一致 ✅
- `fetch_news` 节点在 `nodes/__init__.py` 和 `builder.py` 中使用同一名称 ✅
