"""Campaign 业务编排：处理落库 + 桥接到 AI Service。"""
from __future__ import annotations

import json
import uuid
from typing import Any, AsyncIterator, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend_api.models import Campaign, ContentAsset
from backend_api.services.ai_client import get_ai_client
from shared_libs.schemas import (
    CampaignResponse,
    CampaignStatus,
)


_STAGE_TO_STATUS = {
    "awaiting_topic": CampaignStatus.PENDING_TOPIC,
    "awaiting_review": CampaignStatus.PENDING_REVIEW,
    "running": CampaignStatus.GENERATING,
    "completed": CampaignStatus.COMPLETED,
    "failed": CampaignStatus.FAILED,
}


def _stage_to_status(stage: str) -> CampaignStatus:
    return _STAGE_TO_STATUS.get(stage, CampaignStatus.GENERATING)


def _sse(payload: dict[str, Any]) -> str:
    """打包成一条 SSE 消息（单 data 行）。"""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _to_response(c: Campaign, workflow_state: Optional[dict[str, Any]] = None) -> CampaignResponse:
    return CampaignResponse(
        id=c.id,
        title=c.title,
        context=c.context,
        status=CampaignStatus(c.status),
        thread_id=c.thread_id,
        created_at=c.created_at,
        updated_at=c.updated_at,
        workflow_state=workflow_state,
    )


class CampaignService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.ai = get_ai_client()

    async def create(self, context: str, title: Optional[str]) -> CampaignResponse:
        campaign_id = uuid.uuid4().hex
        thread_id = uuid.uuid4().hex

        campaign = Campaign(
            id=campaign_id,
            title=title,
            context=context,
            status=CampaignStatus.GENERATING.value,
            thread_id=thread_id,
        )
        self.session.add(campaign)
        await self.session.commit()
        await self.session.refresh(campaign)

        # 启动 AI 工作流（应该停在选题中断点）
        wf_state = await self.ai.start_workflow(thread_id=thread_id, context=context)
        campaign.status = _stage_to_status(wf_state["stage"]).value
        await self.session.commit()
        await self.session.refresh(campaign)
        return _to_response(campaign, wf_state)

    async def list_all(self) -> list[CampaignResponse]:
        rows = (await self.session.execute(select(Campaign).order_by(Campaign.created_at.desc()))).scalars().all()
        return [_to_response(r) for r in rows]

    async def get(self, campaign_id: str) -> CampaignResponse:
        c = await self._must_get(campaign_id)
        wf_state = await self.ai.get_state(c.thread_id)
        return _to_response(c, wf_state)

    async def submit_topic(self, campaign_id: str, selected_topic: str) -> CampaignResponse:
        c = await self._must_get(campaign_id)
        wf_state = await self.ai.resume_workflow(
            c.thread_id, {"selected_topic": selected_topic}
        )
        c.status = _stage_to_status(wf_state["stage"]).value
        await self.session.commit()
        await self.session.refresh(c)
        return _to_response(c, wf_state)

    async def _resume_stream(
        self, campaign_id: str, payload: dict[str, Any]
    ) -> AsyncIterator[str]:
        """通用流式恢复：透传节点事件 / 文案增量，结束后落库并发出 done。

        产出已是 SSE 文本，直接交给 StreamingResponse。
        """
        try:
            c = await self._must_get(campaign_id)
            async for evt in self.ai.resume_workflow_stream(c.thread_id, payload):
                etype = evt.get("type")
                if etype in ("delta", "node"):
                    # 节点生命周期与文案增量原样透传给前端
                    yield _sse(evt)
                elif etype == "state":
                    wf = evt.get("workflow_state") or {}
                    stage = wf.get("stage", "running")
                    c.status = _stage_to_status(stage).value
                    await self.session.commit()
                    if stage == "completed":
                        await self._persist_final_asset(
                            campaign_id, wf.get("state") or {}
                        )
                    await self.session.refresh(c)
                    yield _sse(
                        {
                            "type": "done",
                            "campaign": _to_response(c, wf).model_dump(mode="json"),
                        }
                    )
                elif etype == "error":
                    yield _sse(
                        {"type": "error", "message": evt.get("message", "执行失败")}
                    )
        except Exception as exc:  # noqa: BLE001
            detail = getattr(exc, "detail", None) or str(exc)
            yield _sse({"type": "error", "message": str(detail)})

    def submit_topic_stream(
        self, campaign_id: str, selected_topic: str
    ) -> AsyncIterator[str]:
        """流式提交选题。"""
        return self._resume_stream(campaign_id, {"selected_topic": selected_topic})

    def submit_review_stream(
        self, campaign_id: str, decision: str, feedback: Optional[str]
    ) -> AsyncIterator[str]:
        """流式提交审核结果（approve / reject）。"""
        payload: dict[str, Any] = {"decision": decision}
        if decision == "reject":
            payload["feedback"] = feedback
        return self._resume_stream(campaign_id, payload)

    async def submit_review(
        self, campaign_id: str, decision: str, feedback: Optional[str]
    ) -> CampaignResponse:
        c = await self._must_get(campaign_id)
        payload = {"decision": decision}
        if decision == "reject":
            payload["feedback"] = feedback
        wf_state = await self.ai.resume_workflow(c.thread_id, payload)

        c.status = _stage_to_status(wf_state["stage"]).value
        await self.session.commit()

        # 如果工作流走到 completed，落最终 asset
        if wf_state["stage"] == "completed":
            await self._persist_final_asset(campaign_id, wf_state["state"])

        await self.session.refresh(c)
        return _to_response(c, wf_state)

    async def _persist_final_asset(self, campaign_id: str, state: dict[str, Any]) -> None:
        existing = (
            await self.session.execute(
                select(ContentAsset).where(ContentAsset.campaign_id == campaign_id)
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.article = state.get("draft_article")
            existing.image_prompts = state.get("image_prompts") or []
            existing.image_urls = state.get("generated_images") or []
        else:
            asset = ContentAsset(
                id=uuid.uuid4().hex,
                campaign_id=campaign_id,
                article=state.get("draft_article"),
                image_prompts=state.get("image_prompts") or [],
                image_urls=state.get("generated_images") or [],
            )
            self.session.add(asset)
        await self.session.commit()

    async def _must_get(self, campaign_id: str) -> Campaign:
        c = (
            await self.session.execute(select(Campaign).where(Campaign.id == campaign_id))
        ).scalar_one_or_none()
        if c is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="campaign not found")
        return c
