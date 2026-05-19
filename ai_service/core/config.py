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


@lru_cache
def get_settings() -> AIServiceSettings:
    return AIServiceSettings()
