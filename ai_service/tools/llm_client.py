"""LLM 统一接口封装。

- use_mock_llm=True：返回预置 mock 数据，不依赖外部 LLM 即可跑通 LangGraph 流程。
- use_mock_llm=False：调用火山方舟 (Ark) 大模型，OpenAI 兼容的 responses 接口。

真实 prompt 来自 ai_service/prompts/*.yaml。
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from openai import AsyncOpenAI

from ai_service.core.config import get_settings
from ai_service.prompts import get_prompt


def _parse_json_array(text: str) -> list[str]:
    """从 LLM 文本里尽力解析出一个字符串数组。

    兼容三种情况：纯 JSON、被 ```json 围栏包裹、以及退化的逐行列表。
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned).strip()

    candidates = [cleaned]
    match = re.search(r"\[.*\]", cleaned, re.DOTALL)
    if match:
        candidates.append(match.group(0))

    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, list):
            return [str(x).strip() for x in data if str(x).strip()]

    # 退化：按行切分，去掉序号 / 项目符号
    lines = []
    for line in cleaned.splitlines():
        item = re.sub(r"^\s*[-*\d.、)]+\s*", "", line).strip().strip('",')
        if item:
            lines.append(item)
    return lines


class LLMClient:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._client: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            if not self._settings.ark_api_key:
                raise RuntimeError(
                    "USE_MOCK_LLM=false 时必须配置 ARK_API_KEY（见 .env）"
                )
            self._client = AsyncOpenAI(
                base_url=self._settings.ark_base_url,
                api_key=self._settings.ark_api_key,
            )
        return self._client

    async def _complete(self, prompt_name: str, **fields: str) -> str:
        """加载 prompt 配置 -> 拼接 -> 调用 Ark -> 返回正文。"""
        prompt = get_prompt(prompt_name)
        system = prompt["system"].strip()
        user = prompt["user_template"].format(**fields).strip()

        response = await self._get_client().responses.create(
            model=self._settings.ark_model,
            instructions=system,
            input=user,
        )
        return (response.output_text or "").strip()

    async def generate_topics(self, context: str) -> list[str]:
        if self._settings.use_mock_llm:
            await asyncio.sleep(0.05)
            return [
                f"【Mock】当下利率环境下普通家庭的资产配置策略 - 基于：{context[:20]}",
                "【Mock】美联储议息会议背后的 A 股投资机会",
                "【Mock】黄金、美债、比特币：避险三剑客谁更值得持有？",
                "【Mock】消费降级周期里，被错杀的三个核心赛道",
                "【Mock】解读最新 CPI 数据：通胀拐点是否真的来了",
            ]
        text = await self._complete("topic_generator", context=context)
        return _parse_json_array(text)

    async def generate_article(self, selected_topic: str, context: str) -> str:
        if self._settings.use_mock_llm:
            await asyncio.sleep(0.05)
            return (
                f"# 【Mock 草稿】{selected_topic}\n\n"
                f"（基于背景：{context}）\n\n"
                "一、市场回顾：\n这是一段约 1200 字的金融长文的 mock 占位内容，"
                "用于在不调用真实大模型的情况下验证 LangGraph 流程。\n\n"
                "二、核心观点：\n1. 观点一占位；2. 观点二占位；3. 观点三占位。\n\n"
                "三、风险提示：\n本文为 mock 数据，不构成投资建议。\n\n"
                "四、对普通投资者的建议：\n保持节奏，控制仓位，长期主义。"
            )
        return await self._complete(
            "article_writer", selected_topic=selected_topic, context=context
        )

    async def revise_article(self, draft_article: str, human_feedback: str) -> str:
        if self._settings.use_mock_llm:
            await asyncio.sleep(0.05)
            return (
                "# 【Mock 修订稿】\n\n"
                f"已根据如下修改意见进行重写：{human_feedback}\n\n"
                f"---原稿摘录---\n{draft_article[:120]}...\n\n"
                "（mock 修订稿正文 1200 字占位）"
            )
        return await self._complete(
            "article_reviser",
            draft_article=draft_article,
            human_feedback=human_feedback,
        )

    async def extract_image_prompts(self, draft_article: str) -> list[str]:
        if self._settings.use_mock_llm:
            await asyncio.sleep(0.05)
            return [
                "【图1】核心观点：利率拐点确认前，现金为王",
                "【图2】核心观点：高股息板块的防御价值正在显现",
                "【图3】核心观点：黄金中长线配置不可忽视",
            ]
        text = await self._complete("image_prompt_extractor", draft_article=draft_article)
        return _parse_json_array(text)


_llm_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client


def reload_llm_client() -> None:
    """测试用：清掉单例（如修改了 settings）。"""
    global _llm_client
    _llm_client = None


__all__: list[Any] = ["LLMClient", "get_llm_client", "reload_llm_client"]
