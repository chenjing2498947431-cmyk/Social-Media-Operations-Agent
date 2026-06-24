"""HTTP client for MCP_Cluster Prompt Registry."""
from __future__ import annotations

import json
from typing import Any

import httpx


class PromptRegistryClient:
    """Fetch and render prompts from shared platform's prompt_registry."""

    def __init__(self, base_url: str, *, timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def get_prompt(
        self,
        project_id: str,
        env: str,
        prompt_key: str,
        *,
        version: str | None = None,
        **variables: str,
    ) -> dict[str, str]:
        payload: dict[str, Any] = {
            "project_id": project_id,
            "env": env,
            "prompt_key": prompt_key,
            "variables": variables,
        }
        if version is not None:
            payload["version"] = version
        async with httpx.AsyncClient(
            base_url=self.base_url, timeout=self.timeout
        ) as client:
            response = await client.post("/api/v1/prompts/render", json=payload)
        if response.status_code >= 400:
            raise RuntimeError(
                f"Prompt registry error {response.status_code}: {response.text}"
            )
        data = response.json()
        rendered = data.get("rendered_content", "{}")
        return json.loads(rendered)
