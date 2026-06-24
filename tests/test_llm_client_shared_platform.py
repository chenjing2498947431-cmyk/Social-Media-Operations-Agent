from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from ai_service.tools.llm_client import LLMClient
from ai_service.tools.shared_platform_client import SharedPlatformLLMResponse


class FakeSharedPlatformClient:
    def __init__(self) -> None:
        self.generate_calls: list[dict] = []
        self.json_generate_calls: list[dict] = []

    async def generate(self, **kwargs):
        self.generate_calls.append(kwargs)
        return SharedPlatformLLMResponse(
            content="共享平台正文",
            usage={"prompt_tokens": 6, "completion_tokens": 7, "total_tokens": 13},
        )

    async def json_generate(self, **kwargs):
        self.json_generate_calls.append(kwargs)
        return SharedPlatformLLMResponse(
            content='{"prompts": ["图文1", "图文2"]}',
            json_content={"prompts": ["图文1", "图文2"]},
            usage={"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
        )


@pytest.mark.asyncio
async def test_complete_uses_shared_platform_when_enabled():
    client = LLMClient()
    fake = FakeSharedPlatformClient()
    client._shared_client = fake
    client._settings.shared_platform_enabled = True

    with patch("ai_service.tools.llm_client.record_token_usage") as record_usage:
        result = await client._complete(
            "xhs_copy_writer",
            selected_topic="美联储加息",
            draft_article="长文",
        )

    assert result == "共享平台正文"
    assert fake.generate_calls[0]["project_id"] == "finance_media"
    assert fake.generate_calls[0]["env"] == "dev"
    assert fake.generate_calls[0]["task_type"] == "xhs_copy_writer"
    assert fake.generate_calls[0]["model_policy_id"] == "finance_xhs_copy_writer"
    assert fake.generate_calls[0]["messages"][0]["role"] == "system"
    record_usage.assert_called_once_with(6, 7)


@pytest.mark.asyncio
async def test_complete_json_uses_shared_platform_when_enabled():
    client = LLMClient()
    fake = FakeSharedPlatformClient()
    client._shared_client = fake
    client._settings.shared_platform_enabled = True

    with patch("ai_service.tools.llm_client.record_token_usage") as record_usage:
        result = await client._complete_json("image_prompt_extractor", draft_article="长文")

    assert json.loads(result) == {"prompts": ["图文1", "图文2"]}
    assert fake.json_generate_calls[0]["task_type"] == "image_prompt_extractor"
    assert fake.json_generate_calls[0]["model_policy_id"] == "finance_image_prompt_json"
    assert fake.json_generate_calls[0]["json_schema"]["required"] == ["prompts"]
    record_usage.assert_called_once_with(3, 4)
