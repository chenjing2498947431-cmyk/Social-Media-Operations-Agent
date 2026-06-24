"""HTTP client for MCP_Cluster shared LLM Gateway."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, AsyncIterator

import httpx


@dataclass
class SharedPlatformLLMResponse:
    content: str
    usage: dict[str, int]
    json_content: dict[str, Any] | None = None
    tool_calls: list[dict[str, Any]] | None = None


class SharedPlatformClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.transport = transport

    async def generate(
        self,
        *,
        project_id: str,
        env: str,
        task_type: str,
        model_policy_id: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
    ) -> SharedPlatformLLMResponse:
        payload: dict[str, Any] = {
                "project_id": project_id,
                "env": env,
                "task_type": task_type,
                "model_policy_id": model_policy_id,
                "messages": messages,
        }
        if tools is not None:
            payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        data = await self._post("/api/v1/llm/generate", payload)
        return SharedPlatformLLMResponse(
            content=data.get("content", ""),
            usage=data.get("usage") or {},
            tool_calls=data.get("tool_calls"),
        )

    async def json_generate(
        self,
        *,
        project_id: str,
        env: str,
        task_type: str,
        model_policy_id: str,
        messages: list[dict[str, Any]],
        json_schema: dict[str, Any],
    ) -> SharedPlatformLLMResponse:
        data = await self._post(
            "/api/v1/llm/json-generate",
            {
                "project_id": project_id,
                "env": env,
                "task_type": task_type,
                "model_policy_id": model_policy_id,
                "messages": messages,
                "json_schema": json_schema,
            },
        )
        return SharedPlatformLLMResponse(
            content=data.get("content", ""),
            usage=data.get("usage") or {},
            json_content=data.get("json_content"),
        )

    async def image_generate(
        self,
        *,
        project_id: str,
        env: str,
        task_type: str,
        model_policy_id: str,
        prompts: list[str],
        size: str = "2K",
    ) -> list[str]:
        data = await self._post(
            "/api/v1/llm/image-generate",
            {
                "project_id": project_id,
                "env": env,
                "task_type": task_type,
                "model_policy_id": model_policy_id,
                "prompts": prompts,
                "size": size,
            },
        )
        return [img["url"] for img in data.get("images", [])]

    async def search_rag(
        self,
        *,
        project_id: str,
        env: str,
        kb_ids: list[str],
        query: str,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        data = await self._post(
            "/api/v1/rag/search",
            {
                "project_id": project_id,
                "env": env,
                "kb_ids": kb_ids,
                "query": query,
                "top_k": top_k,
            },
        )
        return [
            {
                "title": item.get("title", ""),
                "snippet": item.get("content", ""),
                "url": (item.get("metadata") or {}).get("source")
                or (item.get("metadata") or {}).get("source_url")
                or "",
                "source": item.get("source_type", "shared_rag"),
                "score": item.get("score", 0),
            }
            for item in data.get("results", [])
        ]

    async def stream_generate(
        self,
        *,
        project_id: str,
        env: str,
        task_type: str,
        model_policy_id: str,
        messages: list[dict[str, Any]],
    ) -> AsyncIterator[str]:
        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=180.0,
            transport=self.transport,
        ) as client:
            async with client.stream(
                "POST",
                "/api/v1/llm/stream",
                json={
                    "project_id": project_id,
                    "env": env,
                    "task_type": task_type,
                    "model_policy_id": model_policy_id,
                    "messages": messages,
                },
            ) as response:
                if response.status_code >= 400:
                    raise RuntimeError(self._format_error(response))
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            yield data.get("text", "")
                        except json.JSONDecodeError:
                            continue

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            transport=self.transport,
        ) as client:
            response = await client.post(path, json=payload)
        if response.status_code >= 400:
            raise RuntimeError(self._format_error(response))
        return response.json()

    @staticmethod
    def _format_error(response: httpx.Response) -> str:
        try:
            data = response.json()
        except ValueError:
            return f"Shared platform error {response.status_code}: {response.text}"
        error = data.get("error") or {}
        code = error.get("code", "UNKNOWN")
        message = error.get("message", response.text)
        return f"Shared platform error {response.status_code} {code}: {message}"
