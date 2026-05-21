"""绘图 API 封装。

调用火山方舟 (Ark) doubao-seedream 文生图模型，
generate() 接收一组提示词并返回对应的图片 URL。
"""
from __future__ import annotations

import asyncio
from typing import Iterable

from openai import AsyncOpenAI

from ai_service.core.config import get_settings


class ImageGenAPI:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._client: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            if not self._settings.ark_api_key:
                raise RuntimeError("必须配置 ARK_API_KEY（见 .env）")
            self._client = AsyncOpenAI(
                base_url=self._settings.ark_base_url,
                api_key=self._settings.ark_api_key,
            )
        return self._client

    async def _generate_one(self, prompt: str) -> str:
        response = await self._get_client().images.generate(
            model=self._settings.ark_image_model,
            prompt=prompt,
            size="2K",
            response_format="url",
            extra_body={"watermark": True},
        )
        return response.data[0].url

    async def generate(self, prompts: Iterable[str]) -> list[str]:
        prompt_list = list(prompts)
        # 多张图并发生成
        return list(
            await asyncio.gather(*(self._generate_one(p) for p in prompt_list))
        )


_image_api: ImageGenAPI | None = None


def get_image_api() -> ImageGenAPI:
    global _image_api
    if _image_api is None:
        _image_api = ImageGenAPI()
    return _image_api


def reload_image_api() -> None:
    """测试用：清掉单例（如修改了 settings）。"""
    global _image_api
    _image_api = None
