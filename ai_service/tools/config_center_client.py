"""HTTP client for MCP_Cluster Config Center."""
from __future__ import annotations

from typing import Any

import httpx


class ConfigCenterClient:
    """Fetch task configs from shared platform's config_center API."""

    def __init__(self, base_url: str, *, timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def get_task_config(
        self, project_id: str, env: str, task_type: str
    ) -> dict[str, Any]:
        """Fetch task config from GET /api/v1/configs/{project}/{env}/tasks/{task_type}."""
        async with httpx.AsyncClient(
            base_url=self.base_url, timeout=self.timeout
        ) as client:
            response = await client.get(
                f"/api/v1/configs/{project_id}/{env}/tasks/{task_type}"
            )
        if response.status_code >= 400:
            raise RuntimeError(
                f"Config center error {response.status_code}: {response.text}"
            )
        return response.json()
