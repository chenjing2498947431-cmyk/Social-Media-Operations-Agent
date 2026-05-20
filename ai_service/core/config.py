from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class AIServiceSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ai_service_host: str = "0.0.0.0"
    ai_service_port: int = 8100

    langgraph_checkpoint_dsn: Optional[str] = None
    use_mock_llm: bool = True
    use_mock_image: bool = True

    # 火山方舟 (Ark) 大模型配置，OpenAI 兼容接口
    ark_api_key: Optional[str] = None
    ark_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    ark_model: str = "ep-20260516141907-ggmpz"
    # 文生图模型（doubao-seedream）
    ark_image_model: str = "doubao-seedream-4-5-251128"


@lru_cache
def get_settings() -> AIServiceSettings:
    return AIServiceSettings()
