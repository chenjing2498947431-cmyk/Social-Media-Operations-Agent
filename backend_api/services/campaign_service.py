"""Campaign 业务编排：处理落库 + 桥接到 AI Service。"""
from __future__ import annotations

import uuid
from typing import Any, Optional

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
