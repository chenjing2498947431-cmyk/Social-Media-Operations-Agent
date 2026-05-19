from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class CampaignStatus(str, Enum):
    PENDING_TOPIC = "pending_topic"
    PENDING_REVIEW = "pending_review"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


class ReviewDecision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"


class CampaignCreateRequest(BaseModel):
    context: str = Field(
        ...,
        description="每日金融热点 / 用户偏好等输入背景，会进入 LangGraph 的初始 state.context",
        examples=["美联储议息会议召开，A股震荡，黄金创新高，10 年期美债收益率回落"],
    )
    title: Optional[str] = Field(
        default=None,
        description="可选的任务标题，仅用于业务库展示",
        examples=["5月19日金融选题"],
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "context": "美联储议息会议召开，A股震荡，黄金创新高，10 年期美债收益率回落",
                    "title": "5月19日金融选题",
                }
            ]
        }
    )


class SelectTopicRequest(BaseModel):
    selected_topic: str = Field(
        ...,
        description="人工从备选列表中确认的选题，也可以是不在备选中的自定义选题",
        examples=["【Mock】美联储议息会议背后的 A 股投资机会"],
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"selected_topic": "【Mock】美联储议息会议背后的 A 股投资机会"}
            ]
        }
    )


class ReviewArticleRequest(BaseModel):
    decision: ReviewDecision = Field(
        ...,
        description="approve 通过进入图片生成；reject 进入重写循环",
        examples=["reject"],
    )
    feedback: Optional[str] = Field(
        default=None,
        description="decision=reject 时必填的修改意见；approve 时可省略",
        examples=["请增加对黄金避险逻辑的论证，并补一段风险提示"],
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "decision": "reject",
                    "feedback": "请增加对黄金避险逻辑的论证，并补一段风险提示",
                },
                {"decision": "approve"},
            ]
        }
    )


class CampaignResponse(BaseModel):
    id: str = Field(..., description="campaign 主键")
    title: Optional[str] = None
    context: str
    status: CampaignStatus = Field(
        ..., description="campaign 在业务侧的状态，由 ai_service 工作流 stage 映射而来"
    )
    thread_id: str = Field(..., description="对应 LangGraph 的 thread_id，可直接拿来在 AI Service 调试")
    created_at: datetime
    updated_at: datetime
    workflow_state: Optional[dict[str, Any]] = Field(
        default=None,
        description="若包含，即为来自 ai_service 的完整 WorkflowStateResponse（含 interrupt 提示）",
    )
