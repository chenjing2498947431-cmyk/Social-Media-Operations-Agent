from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class BackendSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    backend_api_host: str = "0.0.0.0"
    backend_api_port: int = 8000

    # 业务数据 SQLAlchemy DSN，默认本地 sqlite 方便快速验证
    database_url: str = "sqlite+aiosqlite:///./backend.db"

    # AI Service 地址（backend_api 通过 HTTP 调用 AI 服务）
    ai_service_base_url: str = "http://localhost:8100"

    # 允许跨域访问的前端来源；默认放开，生产可在 .env 用 JSON 数组收敛
    # 例：CORS_ALLOW_ORIGINS=["http://localhost:5173"]
    cors_allow_origins: list[str] = ["*"]


@lru_cache
def get_settings() -> BackendSettings:
    return BackendSettings()
