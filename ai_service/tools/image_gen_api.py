"""绘图 API 封装。
后期可替换为 DALL-E / Midjourney / 国内大模型，
对 LangGraph 节点透明。当前为 mock 实现，仅返回占位 URL。"""
from __future__ import annotations

import asyncio
import hashlib
from typing import Iterable

from ai_service.core.config import get_settings


class ImageGenAPI:
    def __init__(self) -> None:
        self._settings = get_settings()

    async def generate(self, prompts: Iterable[str]) -> list[str]:
        if self._settings.use_mock_image:
            await asyncio.sleep(0.05)
            urls = []
            for idx, p in enumerate(prompts):
                digest = hashlib.md5(p.encode("utf-8")).hexdigest()[:8]
                urls.append(
                    f"https://mock.image.cdn/agent/{idx}-{digest}.png"
                )
            return urls
        raise NotImplementedError("真实绘图 API 尚未接入")


_image_api: ImageGenAPI | None = None


def get_image_api() -> ImageGenAPI:
    global _image_api
    if _image_api is None:
        _image_api = ImageGenAPI()
    return _image_api
