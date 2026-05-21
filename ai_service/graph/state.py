"""LangGraph 全局状态定义。"""
from __future__ import annotations

from operator import add
from typing import Annotated, Optional, TypedDict


class AgentState(TypedDict, total=False):
    # 输入背景：每日金融热点 / 用户偏好
    context: str

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
    # {node, label, started_at, duration_ms, input_tokens, output_tokens, total_tokens, llm_calls}
    # add reducer 让指标跨节点累加（改写循环会多次追加 revise_article）
    node_metrics: Annotated[list[dict], add]
