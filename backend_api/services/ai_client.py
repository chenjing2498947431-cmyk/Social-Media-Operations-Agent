"""调用 ai_service 的薄封装。"""
from __future__ import annotations

from typing import Any

import httpx

from backend_api.core.config import get_settings


class AIServiceClient:
    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = base_url or get_settings().ai_service_base_url

    async def start_workflow(self, thread_id: str, context: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                f"{self._base_url}/ai/v1/workflows",
                json={"thread_id": thread_id, "context": context},
            )
            r.raise_for_status()
            return r.json()

    async def resume_workflow(self, thread_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(
                f"{self._base_url}/ai/v1/workflows/{thread_id}/resume",
                json={"payload": payload},
            )
            r.raise_for_status()
            return r.json()

    async def get_state(self, thread_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(f"{self._base_url}/ai/v1/workflows/{thread_id}/state")
            r.raise_for_status()
            return r.json()


_client: AIServiceClient | None = None


def get_ai_client() -> AIServiceClient:
    global _client
    if _client is None:
        _client = AIServiceClient()
    return _client
