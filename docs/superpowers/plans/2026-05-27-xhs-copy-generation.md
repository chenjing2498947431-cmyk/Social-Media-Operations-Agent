# 小红书文案生成 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在图片生成后自动追加一个 `generate_xhs_copy` 节点，将小红书风格文案（标题+正文+话题标签）写入 `state.xhs_copy`，工作流随后进入 `END`。

**Architecture:** 仅在末尾串行追加一个节点（`generate_images → generate_xhs_copy → END`），不改动任何已有节点或条件边。新增 `xhs_copy: Optional[str]` 到 `AgentState`，新增 `xhs_copy_writer` prompt，新增 `LLMClient.generate_xhs_copy()` 方法，新增同名节点函数并注册进图。

**Tech Stack:** Python 3.11, LangGraph, 火山方舟 OpenAI-compat API, pytest + pytest-asyncio, PyYAML

---

## 文件结构

| 文件 | 变更类型 | 职责 |
|------|----------|------|
| `ai_service/graph/state.py` | 修改 | 新增 `xhs_copy` 字段 |
| `ai_service/prompts/writer_prompts.yaml` | 修改 | 新增 `xhs_copy_writer` prompt |
| `ai_service/tools/llm_client.py` | 修改 | 新增 `generate_xhs_copy()` 方法 |
| `ai_service/graph/nodes/image_node.py` | 修改 | 新增 `generate_xhs_copy` 节点函数 |
| `ai_service/graph/nodes/__init__.py` | 修改 | 导出新节点 |
| `ai_service/graph/builder.py` | 修改 | 注册节点，改边 `generate_images→END` 为 `generate_images→generate_xhs_copy→END` |
| `ai_service/core/metrics.py` | 修改 | 新增 `"generate_xhs_copy"` 标签 |
| `tests/test_state.py` | 修改 | 新增字段存在断言 |
| `tests/test_llm_client_xhs.py` | 新建 | LLMClient 方法测试 |
| `tests/test_xhs_node.py` | 新建 | 节点函数测试 |

---

## Task 1: AgentState 新字段 + xhs_copy_writer Prompt

**Files:**
- Modify: `ai_service/graph/state.py`
- Modify: `ai_service/prompts/writer_prompts.yaml`
- Modify: `tests/test_state.py`

- [ ] **Step 1: 写失败的测试（字段存在性）**

打开 `tests/test_state.py`，在文件末尾追加：

```python
def test_xhs_copy_field_in_agent_state():
    """xhs_copy 字段存在于 AgentState 注解中。"""
    import typing
    hints = typing.get_type_hints(AgentState)
    assert "xhs_copy" in hints
```

> `AgentState` 已在该文件头部导入，无需重复 import。

- [ ] **Step 2: 运行测试，确认失败**

```powershell
cd d:\Code\Media_Agent\financial_agent_project
D:\Anaconda3\envs\media\python.exe -m pytest tests/test_state.py::test_xhs_copy_field_in_agent_state -v
```

期望：`FAILED` 并提示 `AssertionError`（字段不存在）

- [ ] **Step 3: 在 AgentState 里新增字段**

打开 `ai_service/graph/state.py`，在 `generated_images: list[str]` 后面追加一行：

当前（第 26 行区域）：
```python
    # 图片环节
    image_prompts: list[str]
    generated_images: list[str]

    # 工作流状态
```

改为：
```python
    # 图片环节
    image_prompts: list[str]
    generated_images: list[str]
    xhs_copy: Optional[str]       # 小红书文案（generate_xhs_copy 节点写入）

    # 工作流状态
```

- [ ] **Step 4: 运行测试，确认通过**

```powershell
D:\Anaconda3\envs\media\python.exe -m pytest tests/test_state.py -v
```

期望：全部 PASS

- [ ] **Step 5: 添加 xhs_copy_writer prompt**

打开 `ai_service/prompts/writer_prompts.yaml`，在文件末尾追加：

```yaml

xhs_copy_writer:
  system: |
    你是小红书爆款金融内容创作者，擅长把专业分析转化为普通投资者爱看的帖子。
    格式要求：
    - 第一行：抓眼球的标题（带 emoji，不超过 20 字）
    - 空一行后写正文：分 3-5 段，每段 2-4 句，语气轻松有温度
    - 适量使用 emoji（每段 1-2 个，不滥用）
    - 最后一行：5-8 个话题标签，# 开头，空格分隔
    - 总字数 250-450 字
  user_template: |
    选题：{selected_topic}

    参考长文（提炼精华，勿照搬原文）：
    {draft_article}

    请直接输出小红书帖子正文。
```

- [ ] **Step 6: 验证 YAML 可以被 prompt loader 读取**

```powershell
D:\Anaconda3\envs\media\python.exe -c "
import sys; sys.path.insert(0, '.')
from ai_service.prompts import get_prompt
p = get_prompt('xhs_copy_writer')
print('system keys:', list(p.keys()))
assert '{selected_topic}' in p['user_template'], 'placeholder missing'
assert '{draft_article}' in p['user_template'], 'placeholder missing'
print('OK')
"
```

期望输出：`system keys: ['system', 'user_template']` 和 `OK`

- [ ] **Step 7: Commit**

```powershell
git -C d:\Code\Media_Agent\financial_agent_project add ai_service/graph/state.py ai_service/prompts/writer_prompts.yaml tests/test_state.py
git -C d:\Code\Media_Agent\financial_agent_project commit -m "feat: add xhs_copy field to AgentState and xhs_copy_writer prompt"
```

---

## Task 2: LLMClient.generate_xhs_copy() 方法

**Files:**
- Modify: `ai_service/tools/llm_client.py`
- Create: `tests/test_llm_client_xhs.py`

- [ ] **Step 1: 写失败的测试**

新建 `tests/test_llm_client_xhs.py`：

```python
"""Tests for LLMClient.generate_xhs_copy."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from ai_service.tools.llm_client import LLMClient


@pytest.mark.asyncio
async def test_generate_xhs_copy_calls_correct_prompt():
    """generate_xhs_copy 以 xhs_copy_writer 为 prompt 名，传入 selected_topic 和 draft_article。"""
    client = LLMClient()

    with patch.object(client, "_complete", new_callable=AsyncMock) as mock_complete:
        mock_complete.return_value = "📈 测试标题\n\n正文内容\n\n#A股 #测试"
        result = await client.generate_xhs_copy(
            selected_topic="美联储加息对A股影响",
            draft_article="这是一篇关于美联储的长文...",
        )

    mock_complete.assert_called_once_with(
        "xhs_copy_writer",
        selected_topic="美联储加息对A股影响",
        draft_article="这是一篇关于美联储的长文...",
    )
    assert result == "📈 测试标题\n\n正文内容\n\n#A股 #测试"


@pytest.mark.asyncio
async def test_generate_xhs_copy_returns_string():
    """返回值是字符串，直接透传 _complete 的结果。"""
    client = LLMClient()

    with patch.object(client, "_complete", new_callable=AsyncMock) as mock_complete:
        mock_complete.return_value = "小红书文案内容"
        result = await client.generate_xhs_copy(
            selected_topic="选题",
            draft_article="长文",
        )

    assert isinstance(result, str)
    assert result == "小红书文案内容"
```

- [ ] **Step 2: 运行测试，确认失败**

```powershell
D:\Anaconda3\envs\media\python.exe -m pytest tests/test_llm_client_xhs.py -v
```

期望：`FAILED`，提示 `AttributeError: 'LLMClient' object has no attribute 'generate_xhs_copy'`

- [ ] **Step 3: 在 LLMClient 中新增方法**

打开 `ai_service/tools/llm_client.py`，在 `extract_image_prompts` 方法后面（第 191 行之后）追加：

```python
    async def generate_xhs_copy(
        self,
        selected_topic: str,
        draft_article: str,
    ) -> str:
        """根据选题和已审核长文生成小红书风格帖子（标题+正文+话题标签）。"""
        return await self._complete(
            "xhs_copy_writer",
            selected_topic=selected_topic,
            draft_article=draft_article,
        )
```

- [ ] **Step 4: 运行测试，确认通过**

```powershell
D:\Anaconda3\envs\media\python.exe -m pytest tests/test_llm_client_xhs.py -v
```

期望：2 个 PASS

- [ ] **Step 5: Commit**

```powershell
git -C d:\Code\Media_Agent\financial_agent_project add ai_service/tools/llm_client.py tests/test_llm_client_xhs.py
git -C d:\Code\Media_Agent\financial_agent_project commit -m "feat: add LLMClient.generate_xhs_copy() method"
```

---

## Task 3: generate_xhs_copy 节点 + 接入 Graph

**Files:**
- Modify: `ai_service/graph/nodes/image_node.py`
- Modify: `ai_service/core/metrics.py`
- Modify: `ai_service/graph/nodes/__init__.py`
- Modify: `ai_service/graph/builder.py`
- Create: `tests/test_xhs_node.py`

- [ ] **Step 1: 写失败的测试**

新建 `tests/test_xhs_node.py`：

```python
"""generate_xhs_copy 节点单元测试。"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from ai_service.graph.nodes.image_node import generate_xhs_copy


@pytest.mark.asyncio
async def test_generate_xhs_copy_writes_to_state():
    """节点正常执行时，xhs_copy 写入返回 dict，status=completed。"""
    state = {
        "selected_topic": "美联储加息对A股影响",
        "draft_article": "这是一篇长文...",
        "status": "running",
        "node_metrics": [],
    }

    with patch("ai_service.graph.nodes.image_node.get_llm_client") as mock_get:
        mock_llm = AsyncMock()
        mock_llm.generate_xhs_copy = AsyncMock(return_value="📈 测试文案\n\n#A股 #投资")
        mock_get.return_value = mock_llm

        result = await generate_xhs_copy(state)

    assert result["xhs_copy"] == "📈 测试文案\n\n#A股 #投资"
    assert result["status"] == "completed"
    mock_llm.generate_xhs_copy.assert_called_once_with(
        selected_topic="美联储加息对A股影响",
        draft_article="这是一篇长文...",
    )


@pytest.mark.asyncio
async def test_generate_xhs_copy_handles_missing_state_fields():
    """state 中没有 selected_topic / draft_article 时，传空字符串，不报错。"""
    state = {
        "status": "running",
        "node_metrics": [],
    }

    with patch("ai_service.graph.nodes.image_node.get_llm_client") as mock_get:
        mock_llm = AsyncMock()
        mock_llm.generate_xhs_copy = AsyncMock(return_value="文案")
        mock_get.return_value = mock_llm

        result = await generate_xhs_copy(state)

    mock_llm.generate_xhs_copy.assert_called_once_with(
        selected_topic="",
        draft_article="",
    )
    assert result["xhs_copy"] == "文案"
```

- [ ] **Step 2: 运行测试，确认失败**

```powershell
D:\Anaconda3\envs\media\python.exe -m pytest tests/test_xhs_node.py -v
```

期望：`FAILED`，提示 `ImportError: cannot import name 'generate_xhs_copy'`

- [ ] **Step 3: 在 image_node.py 追加节点函数**

打开 `ai_service/graph/nodes/image_node.py`，在文件末尾追加：

```python


@track_node("generate_xhs_copy")
async def generate_xhs_copy(state: AgentState) -> dict:
    """根据已审核长文生成小红书风格文案，写入 state.xhs_copy。"""
    llm = get_llm_client()
    copy_text = await llm.generate_xhs_copy(
        selected_topic=state.get("selected_topic", ""),
        draft_article=state.get("draft_article", ""),
    )
    return {
        "xhs_copy": copy_text,
        "status": "completed",
    }
```

- [ ] **Step 4: 在 metrics.py 的 NODE_LABELS 新增标签**

打开 `ai_service/core/metrics.py`，在 `NODE_LABELS` 字典末尾追加一行：

当前：
```python
NODE_LABELS: dict[str, str] = {
    "fetch_news": "新闻搜索",
    "generate_topics": "选题生成",
    "generate_article": "文案撰写",
    "revise_article": "文案改写",
    "extract_image_content": "配图文案提炼",
    "generate_images": "配图生成",
}
```

改为：
```python
NODE_LABELS: dict[str, str] = {
    "fetch_news": "新闻搜索",
    "generate_topics": "选题生成",
    "generate_article": "文案撰写",
    "revise_article": "文案改写",
    "extract_image_content": "配图文案提炼",
    "generate_images": "配图生成",
    "generate_xhs_copy": "小红书文案生成",
}
```

- [ ] **Step 5: 运行节点测试，确认通过**

```powershell
D:\Anaconda3\envs\media\python.exe -m pytest tests/test_xhs_node.py -v
```

期望：2 个 PASS

- [ ] **Step 6: 导出新节点**

打开 `ai_service/graph/nodes/__init__.py`，全文替换为：

```python
from .fetch_news_node import fetch_news
from .topic_node import generate_topics, human_select_topic
from .writer_node import generate_article
from .critic_node import human_review_article, revise_article
from .image_node import extract_image_content, generate_images, generate_xhs_copy

__all__ = [
    "fetch_news",
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

- [ ] **Step 7: 在 builder.py 注册节点并修改边**

打开 `ai_service/graph/builder.py`，做两处修改：

**7a. imports 行** — 在 `generate_images,` 后面加 `generate_xhs_copy,`：

当前：
```python
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
```

改为：
```python
from ai_service.graph.nodes import (
    fetch_news,
    generate_topics,
    human_select_topic,
    generate_article,
    human_review_article,
    revise_article,
    extract_image_content,
    generate_images,
    generate_xhs_copy,
)
```

**7b. build_graph() 函数体** — 在 `builder.add_node("generate_images", generate_images)` 后面追加节点注册，并把末尾的边从 `generate_images → END` 改为 `generate_images → generate_xhs_copy → END`：

当前：
```python
    builder.add_node("extract_image_content", extract_image_content)
    builder.add_node("generate_images", generate_images)

    builder.add_edge(START, "fetch_news")
    ...
    builder.add_edge("extract_image_content", "generate_images")
    builder.add_edge("generate_images", END)
```

改为：
```python
    builder.add_node("extract_image_content", extract_image_content)
    builder.add_node("generate_images", generate_images)
    builder.add_node("generate_xhs_copy", generate_xhs_copy)

    builder.add_edge(START, "fetch_news")
    ...
    builder.add_edge("extract_image_content", "generate_images")
    builder.add_edge("generate_images", "generate_xhs_copy")
    builder.add_edge("generate_xhs_copy", END)
```

- [ ] **Step 8: 全量测试**

```powershell
D:\Anaconda3\envs\media\python.exe -m pytest tests/ -v
```

期望：全部 PASS（包括 test_state, test_web_search, test_fetch_news_node, test_llm_client_topics, test_topic_node, test_llm_client_xhs, test_xhs_node）

- [ ] **Step 9: Commit**

```powershell
git -C d:\Code\Media_Agent\financial_agent_project add ai_service/graph/nodes/image_node.py ai_service/core/metrics.py ai_service/graph/nodes/__init__.py ai_service/graph/builder.py tests/test_xhs_node.py
git -C d:\Code\Media_Agent\financial_agent_project commit -m "feat: add generate_xhs_copy node and wire into graph (generate_images -> generate_xhs_copy -> END)"
```

---

## 完成标准检查

运行所有测试后确认：

1. `tests/` 下全部测试通过
2. `GET /{thread_id}/state` 返回的 `state` 中有 `xhs_copy` 字段（完成流程后为字符串，未开始时为 `null`）
3. `node_metrics` 末尾新增 `{"node": "generate_xhs_copy", "label": "小红书文案生成", ...}` 一条记录
