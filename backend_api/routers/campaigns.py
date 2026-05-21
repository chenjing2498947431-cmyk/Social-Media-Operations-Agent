from __future__ import annotations

from fastapi import APIRouter, Depends, Path
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend_api.core.database import get_session
from backend_api.services.campaign_service import CampaignService
from shared_libs.schemas import (
    CampaignCreateRequest,
    CampaignResponse,
    ReviewArticleRequest,
    SelectTopicRequest,
)

router = APIRouter(prefix="/api/v1/campaigns", tags=["campaigns"])


def _service(session: AsyncSession = Depends(get_session)) -> CampaignService:
    return CampaignService(session)


_CAMPAIGN_ID = Path(..., description="campaign 主键", examples=["a1b2c3d4..."])


@router.post(
    "",
    response_model=CampaignResponse,
    summary="① 创建 campaign，启动工作流",
    response_description="新建的 campaign，status 通常为 pending_topic，workflow_state.interrupt 中携带备选选题",
    description=(
        "调用 ai_service 启动 LangGraph，并把 thread_id 落库。\n\n"
        "成功后 workflow 会自动跑到第一个中断点（选题确认），返回的 "
        "`workflow_state.interrupt.topics` 即为给运营人员的备选选题。\n\n"
        "**下一步**：调 `POST /api/v1/campaigns/{id}/select-topic`。"
    ),
)
async def create_campaign(
    req: CampaignCreateRequest, svc: CampaignService = Depends(_service)
) -> CampaignResponse:
    return await svc.create(context=req.context, title=req.title)


@router.get(
    "",
    response_model=list[CampaignResponse],
    summary="列出所有 campaign（不含 workflow_state）",
    description="按创建时间倒序返回。需要拿到 workflow_state 时请走详情接口。",
)
async def list_campaigns(svc: CampaignService = Depends(_service)) -> list[CampaignResponse]:
    return await svc.list_all()


@router.get(
    "/{campaign_id}",
    response_model=CampaignResponse,
    summary="campaign 详情（含最新 workflow_state）",
    description="每次都会向 ai_service 拉一次最新 state，确保前端拿到准确的中断信息。",
)
async def get_campaign(
    campaign_id: str = _CAMPAIGN_ID,
    svc: CampaignService = Depends(_service),
) -> CampaignResponse:
    return await svc.get(campaign_id)


@router.post(
    "/{campaign_id}/select-topic",
    response_model=CampaignResponse,
    summary="② 提交人工选定的选题",
    response_description="进入审核阶段，workflow_state.interrupt 中携带草稿正文",
    description=(
        "把人工确认的选题喂给 LangGraph，触发文案生成节点。\n\n"
        "**前置条件**：当前 status 必须是 `pending_topic`。\n\n"
        "**下一步**：拿到 `workflow_state.interrupt.draft_article` 让运营人员审核，"
        "再调 `POST /{id}/review-article`。"
    ),
)
async def select_topic(
    req: SelectTopicRequest,
    campaign_id: str = _CAMPAIGN_ID,
    svc: CampaignService = Depends(_service),
) -> CampaignResponse:
    return await svc.submit_topic(campaign_id, req.selected_topic)


@router.post(
    "/{campaign_id}/select-topic/stream",
    summary="②（流式）提交选题：边生成文案边推送",
    response_description="text/event-stream：逐段返回文案，完成后推送更新后的 campaign",
    description=(
        "SSE 流式版 select-topic，前置条件同 `/select-topic`（status=pending_topic）。\n\n"
        "事件（`data:` 行，JSON 含 `type`）：`delta` 文案增量 / `done` 完成（带 campaign）/ "
        "`error` 异常。"
    ),
)
async def select_topic_stream(
    req: SelectTopicRequest,
    campaign_id: str = _CAMPAIGN_ID,
    svc: CampaignService = Depends(_service),
) -> StreamingResponse:
    return StreamingResponse(
        svc.submit_topic_stream(campaign_id, req.selected_topic),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/{campaign_id}/review-article",
    response_model=CampaignResponse,
    summary="③ 提交人工审核结果（approve / reject）",
    response_description=(
        "若 approve：status=completed，state 中含 image_prompts + generated_images；"
        "若 reject：status 仍为 pending_review，state.draft_article 已被重写，revision_round +1"
    ),
    description=(
        "**前置条件**：当前 status 必须是 `pending_review`。\n\n"
        "- `decision=approve`：直接走到图片生成 → END。\n"
        "- `decision=reject` 且填 `feedback`：进入 revise 节点，重写后再次停在审核中断点，"
        "可以反复调本接口直到 approve。"
    ),
)
async def review_article(
    req: ReviewArticleRequest,
    campaign_id: str = _CAMPAIGN_ID,
    svc: CampaignService = Depends(_service),
) -> CampaignResponse:
    return await svc.submit_review(campaign_id, req.decision.value, req.feedback)


@router.post(
    "/{campaign_id}/review-article/stream",
    summary="③（流式）提交审核结果：实时回传节点运行过程",
    response_description="text/event-stream：节点事件，完成后推送更新后的 campaign",
    description=(
        "SSE 流式版 review-article，前置条件同 `/review-article`。\n\n"
        "事件（`data:` 行，JSON 含 `type`）：`node` 节点开始/结束 / `done` 完成（带 "
        "campaign）/ `error` 异常。"
    ),
)
async def review_article_stream(
    req: ReviewArticleRequest,
    campaign_id: str = _CAMPAIGN_ID,
    svc: CampaignService = Depends(_service),
) -> StreamingResponse:
    return StreamingResponse(
        svc.submit_review_stream(campaign_id, req.decision.value, req.feedback),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
