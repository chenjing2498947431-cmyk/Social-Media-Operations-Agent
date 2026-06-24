from __future__ import annotations

import json

import httpx
import pytest

from ai_service.tools.shared_platform_client import SharedPlatformClient


@pytest.mark.asyncio
async def test_generate_posts_to_shared_llm_gateway():
    seen: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "content": "生成结果",
                "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
            },
        )

    client = SharedPlatformClient("http://shared.local", transport=httpx.MockTransport(handler))

    result = await client.generate(
        project_id="finance_media",
        env="dev",
        task_type="generate_article",
        model_policy_id="finance_high_quality",
        messages=[{"role": "user", "content": "hello"}],
    )

    assert seen["path"] == "/api/v1/llm/generate"
    assert seen["payload"]["project_id"] == "finance_media"
    assert result.content == "生成结果"
    assert result.usage["total_tokens"] == 5


@pytest.mark.asyncio
async def test_json_generate_returns_json_content():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/llm/json-generate"
        return httpx.Response(
            200,
            json={
                "content": '{"prompts": ["图1"]}',
                "json_content": {"prompts": ["图1"]},
                "usage": {"prompt_tokens": 4, "completion_tokens": 5, "total_tokens": 9},
            },
        )

    client = SharedPlatformClient("http://shared.local", transport=httpx.MockTransport(handler))

    result = await client.json_generate(
        project_id="finance_media",
        env="dev",
        task_type="generate_article",
        model_policy_id="finance_json_stable",
        messages=[{"role": "user", "content": "hello"}],
        json_schema={"type": "object", "required": ["prompts"]},
    )

    assert result.json_content == {"prompts": ["图1"]}
    assert result.usage["prompt_tokens"] == 4


@pytest.mark.asyncio
async def test_shared_platform_error_raises_runtime_error():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={"error": {"code": "MODEL_POLICY_NOT_FOUND", "message": "missing"}},
        )

    client = SharedPlatformClient("http://shared.local", transport=httpx.MockTransport(handler))

    with pytest.raises(RuntimeError, match="MODEL_POLICY_NOT_FOUND"):
        await client.generate(
            project_id="finance_media",
            env="dev",
            task_type="generate_article",
            model_policy_id="missing",
            messages=[],
        )
