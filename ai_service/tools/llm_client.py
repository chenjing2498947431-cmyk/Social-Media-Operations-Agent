"""LLM 统一接口封装。

调用火山方舟 (Ark) 大模型，OpenAI 兼容的 responses 接口。
真实 prompt 来自 ai_service/prompts/*.yaml。
"""
from __future__ import annotations

import json
import re
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from ai_service.core.config import get_settings
from ai_service.core.metrics import record_token_usage
from ai_service.prompts import get_prompt


def _estimate_tokens(text: str) -> int:
    """接口未返回 usage 时的粗略 token 估算。

    中英文混排取折中：约 2 字符 / token。
    """
    if not text:
        return 0
    return max(1, round(len(text) / 2))


def _format_search_results(results: list[dict]) -> str:
    """将 MCP 搜索结果列表格式化为 prompt 可读文本。

    每条格式：
        N. 标题
           摘要
           来源：URL
    """
    if not results:
        return "（搜索暂不可用，仅凭背景信息生成）"
    lines: list[str] = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "")
        snippet = r.get("snippet", "")
        url = r.get("url", "")
        line = f"{i}. {title}"
        if snippet:
            line += f"\n   {snippet}"
        if url:
            line += f"\n   来源：{url}"
        lines.append(line)
    return "\n".join(lines)


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
                raise RuntimeError("必须配置 ARK_API_KEY（见 .env）")
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
        text = (response.output_text or "").strip()

        usage = getattr(response, "usage", None)
        if usage is not None:
            record_token_usage(
                getattr(usage, "input_tokens", 0) or 0,
                getattr(usage, "output_tokens", 0) or 0,
            )
        else:
            record_token_usage(
                _estimate_tokens(system) + _estimate_tokens(user),
                _estimate_tokens(text),
            )
        return text

    async def generate_topics(
        self,
        context: str,
        search_results: list[dict] | None = None,
    ) -> list[str]:
        """根据搜索结果和背景信息生成候选选题列表。"""
        search_context = _format_search_results(search_results or [])
        text = await self._complete(
            "topic_generator",
            context=context,
            search_context=search_context,
        )
        return _parse_json_array(text)

    async def stream_article(
        self, selected_topic: str, context: str
    ) -> AsyncIterator[str]:
        """流式生成文案：逐段 yield 文本增量；结束后上报真实 token 用量。

        仅产出 `response.output_text.delta`（正文），忽略模型的思考摘要增量。
        """
        prompt = get_prompt("article_writer")
        system = prompt["system"].strip()
        user = prompt["user_template"].format(
            selected_topic=selected_topic, context=context
        ).strip()

        stream = await self._get_client().responses.create(
            model=self._settings.ark_model,
            instructions=system,
            input=user,
            stream=True,
        )
        full_text = ""
        usage = None
        async for event in stream:
            etype = getattr(event, "type", "")
            if etype == "response.output_text.delta":
                delta = getattr(event, "delta", "") or ""
                if delta:
                    full_text += delta
                    yield delta
            elif etype == "response.completed":
                usage = getattr(getattr(event, "response", None), "usage", None)

        if usage is not None:
            record_token_usage(
                getattr(usage, "input_tokens", 0) or 0,
                getattr(usage, "output_tokens", 0) or 0,
            )
        else:
            record_token_usage(
                _estimate_tokens(system) + _estimate_tokens(user),
                _estimate_tokens(full_text),
            )

    async def revise_article(self, draft_article: str, human_feedback: str) -> str:
        return await self._complete(
            "article_reviser",
            draft_article=draft_article,
            human_feedback=human_feedback,
        )

    async def extract_image_prompts(self, draft_article: str) -> list[str]:
        text = await self._complete("image_prompt_extractor", draft_article=draft_article)
        return _parse_json_array(text)

    async def generate_xhs_copy(
        self,
        selected_topic: str,
        draft_article: str,
    ) -> str:
        """根据选题和已审核长文生成小红书风格帖子（标题+正文+话题标签）。"""
        return await self._complete(
            "xhs_copy_writer",
            selected_topic=selected_topic,
            draft_article=draft_article,
        )


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


__all__: list[Any] = ["LLMClient", "get_llm_client", "reload_llm_client", "_format_search_results"]
