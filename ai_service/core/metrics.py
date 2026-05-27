"""节点级运行指标采集：耗时 + token 用量。

每个 AI 计算节点用 @track_node 装饰，自动记录：
- 墙钟耗时 (duration_ms)
- 该节点内所有 LLM 调用累计的 token 用量

token 用量由 llm_client 在每次调用后通过 record_token_usage() 上报，
经 ContextVar 关联到「当前正在执行的节点」。节点外调用时静默忽略。

采集到的指标以单元素列表的形式写入 state.node_metrics，
由 AgentState 上的 operator.add reducer 跨节点累加。
"""
from __future__ import annotations

import time
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Awaitable, Callable

from langgraph.config import get_stream_writer

# 当前节点的 token 累加器；不在 @track_node 作用域内时为 None。
_token_sink: ContextVar[dict[str, int] | None] = ContextVar("_token_sink", default=None)

# 节点名 -> 面向运营人员的中文标签
NODE_LABELS: dict[str, str] = {
    "fetch_news": "新闻搜索",          # ← 新增这一行
    "generate_topics": "选题生成",
    "generate_article": "文案撰写",
    "revise_article": "文案改写",
    "extract_image_content": "配图文案提炼",
    "generate_images": "配图生成",
    "generate_xhs_copy": "小红书文案生成",
}

_NodeFn = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


def record_token_usage(input_tokens: int, output_tokens: int) -> None:
    """LLM 客户端每次调用后上报 token 用量，累加到当前节点。

    若不在 @track_node 装饰的节点内（sink 为 None），静默忽略。
    """
    sink = _token_sink.get()
    if sink is None:
        return
    sink["input_tokens"] += int(input_tokens or 0)
    sink["output_tokens"] += int(output_tokens or 0)
    sink["llm_calls"] += 1


def track_node(node_name: str) -> Callable[[_NodeFn], _NodeFn]:
    """装饰异步计算节点：统计耗时与 token，并把指标写入 state.node_metrics。"""

    def decorator(fn: _NodeFn) -> _NodeFn:
        @wraps(fn)
        async def wrapper(state: dict[str, Any]) -> dict[str, Any]:
            sink = {"input_tokens": 0, "output_tokens": 0, "llm_calls": 0}
            token = _token_sink.set(sink)
            label = NODE_LABELS.get(node_name, node_name)

            # 流式运行（astream stream_mode="custom"）时把节点生命周期推给调用方；
            # 非流式（ainvoke）或测试环境时 writer 为 no-op，互不影响。
            try:
                writer = get_stream_writer()
            except RuntimeError:
                writer = lambda _: None  # noqa: E731
            writer({"type": "node", "node": node_name, "label": label, "phase": "start"})

            started_at = datetime.now(timezone.utc)
            t0 = time.perf_counter()
            try:
                result = await fn(state)
            finally:
                _token_sink.reset(token)
            duration_ms = round((time.perf_counter() - t0) * 1000, 1)

            metric = {
                "node": node_name,
                "label": label,
                "started_at": started_at.isoformat(),
                "duration_ms": duration_ms,
                "input_tokens": sink["input_tokens"],
                "output_tokens": sink["output_tokens"],
                "total_tokens": sink["input_tokens"] + sink["output_tokens"],
                "llm_calls": sink["llm_calls"],
            }
            writer(
                {
                    "type": "node",
                    "node": node_name,
                    "label": label,
                    "phase": "end",
                    "metric": metric,
                }
            )
            out = dict(result or {})
            out["node_metrics"] = [metric]
            return out

        return wrapper

    return decorator
