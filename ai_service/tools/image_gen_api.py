"""绘图 API 封装。

调用火山方舟 (Ark) doubao-seedream 文生图模型，
generate() 接收一组提示词并返回对应的图片 URL。
"""
from __future__ import annotations

import asyncio
from typing import Iterable

from openai import AsyncOpenAI

from ai_service.core.config import get_settings
from ai_service.tools.shared_platform_client import SharedPlatformClient
from ai_service.tools.config_center_client import ConfigCenterClient


class ImageGenAPI:
    _MODEL_POLICY_ID = "finance_image_gen"
    _TASK_TYPE = "generate_image"

    def __init__(self) -> None:
        self._settings = get_settings()
        self._client: AsyncOpenAI | None = None
        self._shared_client: SharedPlatformClient | None = None
        self._config_client: ConfigCenterClient | None = None

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            if not self._settings.ark_api_key:
                raise RuntimeError("必须配置 ARK_API_KEY（见 .env）")
            self._client = AsyncOpenAI(
                base_url=self._settings.ark_base_url,
                api_key=self._settings.ark_api_key,
            )
        return self._client

    def _get_shared_client(self) -> SharedPlatformClient:
        if self._shared_client is None:
            self._shared_client = SharedPlatformClient(
                self._settings.shared_platform_base_url,
                timeout=180.0,
            )
        return self._shared_client

    def _get_config_client(self) -> ConfigCenterClient:
        if self._config_client is None:
            self._config_client = ConfigCenterClient(
                self._settings.shared_platform_base_url
            )
        return self._config_client

    async def _resolve_model_policy(self) -> str:
        if not self._settings.shared_platform_enabled:
            return self._MODEL_POLICY_ID
        try:
            config = await self._get_config_client().get_task_config(
                self._settings.shared_platform_project_id,
                self._settings.shared_platform_env,
                self._TASK_TYPE,
            )
            return config.get("model_policy_id", self._MODEL_POLICY_ID)
        except Exception:
            return self._MODEL_POLICY_ID

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
        if self._settings.shared_platform_enabled:
            return await self._get_shared_client().image_generate(
                project_id=self._settings.shared_platform_project_id,
                env=self._settings.shared_platform_env,
                task_type=self._TASK_TYPE,
                model_policy_id=await self._resolve_model_policy(),
                prompts=list(prompts),
            )
        return list(
            await asyncio.gather(*(self._generate_one(p) for p in prompts))
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
