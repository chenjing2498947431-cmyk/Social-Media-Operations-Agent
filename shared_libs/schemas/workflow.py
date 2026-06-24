from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class WorkflowStage(str, Enum):
    """工作流当前停留的阶段（用于前端判断该展示哪种交互）"""
    AWAITING_TOPIC = "awaiting_topic"
    AWAITING_REVIEW = "awaiting_review"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkflowStartRequest(BaseModel):
    thread_id: str = Field(
        ...,
        description="由调用方生成的会话 ID，对应 LangGraph 的 thread_id；调用方需自行保证唯一",
        examples=["thread-demo-001"],
    )
    context: str = Field(
        ...,
        description="进入 state.context 的营销背景文本",
        examples=["新品即将发布，目标客群关注性价比与服务体验，近期社媒讨论热度上升"],
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "thread_id": "thread-demo-001",
                    "context": "新品即将发布，目标客群关注性价比与服务体验，近期社媒讨论热度上升",
                }
            ]
        }
    )


class WorkflowResumeRequest(BaseModel):
    """通用恢复入口。根据当前 interrupt 类型，payload 含义不同：

    - 选题阶段 (interrupt.action == 'select_topic')：
        ```{"selected_topic": "..."}```
    - 审核阶段 (interrupt.action == 'review_article')：
        - 通过：```{"decision": "approve"}```
        - 拒绝并修改：```{"decision": "reject", "feedback": "..."}```
    """
    payload: dict[str, Any] = Field(
        ...,
        description="见上方说明：根据 interrupt.action 决定 schema",
        examples=[{"selected_topic": "【Mock】美联储议息会议背后的 A 股投资机会"}],
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "payload": {
                        "selected_topic": "【Mock】美联储议息会议背后的 A 股投资机会"
                    }
                },
                {
                    "payload": {
                        "decision": "reject",
                        "feedback": "请增加对黄金避险逻辑的论证",
                    }
                },
                {"payload": {"decision": "approve"}},
            ]
        }
    )


class WorkflowStateResponse(BaseModel):
    thread_id: str
    stage: WorkflowStage = Field(
        ...,
        description="awaiting_topic / awaiting_review / running / completed / failed",
    )
    state: dict[str, Any] = Field(
        ...,
        description="LangGraph 当前 checkpoint 的 values（包含 topics / draft_article / generated_images / xhs_copy 等）",
    )
    interrupt: Optional[dict[str, Any]] = Field(
        default=None,
        description=(
            "若处于中断态，前端可据此知道该展示哪种交互。"
            "结构形如 {action: 'select_topic'|'review_article', ...payload}"
        ),
    )
