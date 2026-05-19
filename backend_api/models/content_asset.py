from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend_api.models.base import Base


class ContentAsset(Base):
    """最终生成的长文 + 图片资源。"""
    __tablename__ = "content_assets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    campaign_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("campaigns.id", ondelete="CASCADE"), index=True, nullable=False
    )
    article: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 公众号长文
    image_prompts: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    image_urls: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)  # 小红书图片
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
