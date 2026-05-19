"""LLM 统一接口封装。
当前阶段 use_mock_llm=True 时，所有调用返回预置的 mock 数据，
便于不依赖外部 LLM 即可跑通整条 LangGraph 流程。"""
from __future__ import annotations

import asyncio
from typing import Any

from ai_service.core.config import get_settings


class LLMClient:
    def __init__(self) -> None:
        self._settings = get_settings()

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
        raise NotImplementedError("真实 LLM 调用尚未接入")

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
        raise NotImplementedError("真实 LLM 调用尚未接入")

    async def revise_article(self, draft_article: str, human_feedback: str) -> str:
        if self._settings.use_mock_llm:
            await asyncio.sleep(0.05)
            return (
                "# 【Mock 修订稿】\n\n"
                f"已根据如下修改意见进行重写：{human_feedback}\n\n"
                f"---原稿摘录---\n{draft_article[:120]}...\n\n"
                "（mock 修订稿正文 1200 字占位）"
            )
        raise NotImplementedError("真实 LLM 调用尚未接入")

    async def extract_image_prompts(self, draft_article: str) -> list[str]:
        if self._settings.use_mock_llm:
            await asyncio.sleep(0.05)
            return [
                "【图1】核心观点：利率拐点确认前，现金为王",
                "【图2】核心观点：高股息板块的防御价值正在显现",
                "【图3】核心观点：黄金中长线配置不可忽视",
            ]
        raise NotImplementedError("真实 LLM 调用尚未接入")


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
