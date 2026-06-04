"""LLM 统一接口封装。

调用火山方舟 (Ark) 大模型，OpenAI 兼容的 responses 接口。
真实 prompt 来自 ai_service/prompts/*.yaml。
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, AsyncIterator, Callable

logger = logging.getLogger(__name__)

from langgraph.config import get_stream_writer
from openai import AsyncOpenAI
from pydantic import BaseModel

from ai_service.core.config import get_settings
from ai_service.core.metrics import record_token_usage
from ai_service.prompts import get_prompt

# MCP 工具名到中文标签的映射；未收录的工具直接用工具名展示。
_TOOL_LABELS: dict[str, str] = {
    "brave_web_search": "网页搜索",
    "brave_news_search": "新闻搜索",
}


def _get_writer():
    try:
        return get_stream_writer()
    except RuntimeError:
        return lambda _: None


class _TopicsOutput(BaseModel):
    topics: list[str]


class _PromptsOutput(BaseModel):
    prompts: list[str]


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
        age = r.get("age", "")
        line = f"{i}. {title}"
        if age:
            line += f"（{age}）"
        if snippet:
            line += f"\n   {snippet}"
        if url:
            line += f"\n   来源：{url}"
        lines.append(line)
    return "\n".join(lines)


def _extract_json_obj(text: str) -> dict:
    """从 LLM 输出中提取第一个 JSON 对象，兼容 markdown 代码块包裹。"""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned).strip()
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    raise ValueError(f"无法从 LLM 输出中解析 JSON 对象: {text[:200]}")


_SEARCH_NEWS_TOOL: dict = {
    "type": "function",
    "function": {
        "name": "search_news",
        "description": "搜索最新金融新闻和市场热点。当背景信息不足以生成有时效性的选题时调用。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"}
            },
            "required": ["query"],
        },
    },
}


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

    async def _complete_json(self, prompt_name: str, **fields: str) -> str:
        """加载 prompt 配置 -> 拼接 -> 以 JSON mode 调用 -> 返回 JSON 文本。"""
        prompt = get_prompt(prompt_name)
        system = prompt["system"].strip()
        user = prompt["user_template"].format(**fields).strip()

        response = await self._get_client().chat.completions.create(
            model=self._settings.ark_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        text = (response.choices[0].message.content or "").strip()

        usage = getattr(response, "usage", None)
        if usage is not None:
            record_token_usage(
                getattr(usage, "prompt_tokens", 0) or 0,
                getattr(usage, "completion_tokens", 0) or 0,
            )
        else:
            record_token_usage(
                _estimate_tokens(system) + _estimate_tokens(user),
                _estimate_tokens(text),
            )
        return text

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
        mcp_session: Any | None = None,
        search_fn: Callable | None = None,
    ) -> tuple[list[str], list[dict]]:
        """结合可选的联网工具生成候选选题列表。

        优先使用 mcp_session：通过 tools/list 动态发现工具，让 LLM 自主选择
        调用哪个 MCP 工具（如 brave_web_search / brave_local_search）。

        若仅传 search_fn，则使用旧的 search_news 包装工具（向后兼容）。

        最多循环 2 轮（1 次工具调用 + 1 次生成）。
        无论是否调用工具，均返回 (topics, used_results)。
        """
        prompt = get_prompt("topic_generator")
        system = prompt["system"].strip()
        user = prompt["user_template"].format(context=context).strip()

        messages: list[dict] = [{"role": "user", "content": user}]
        used_results: list[dict] = []
        oai = self._get_client()
        tool_called = False  # only allow one search call per generation

        # Discover available tools: prefer mcp_session, fall back to search_fn shim
        if mcp_session is not None:
            fn_defs = await mcp_session.list_tools()
            tools = [{"type": "function", "function": fn} for fn in fn_defs]
        elif search_fn is not None:
            tools = [_SEARCH_NEWS_TOOL]
        else:
            tools = []

        for _ in range(2):
            create_kwargs: dict = {
                "model": self._settings.ark_model,
                "messages": [{"role": "system", "content": system}] + messages,
            }
            # After a tool call, omit tools so the LLM must produce content
            if tools and not tool_called:
                create_kwargs["tools"] = tools
                create_kwargs["tool_choice"] = "required"

            response = await oai.chat.completions.create(**create_kwargs)

            usage = getattr(response, "usage", None)
            if usage is not None:
                record_token_usage(
                    getattr(usage, "prompt_tokens", 0) or 0,
                    getattr(usage, "completion_tokens", 0) or 0,
                )

            msg = response.choices[0].message

            if msg.tool_calls and not tool_called:
                tool_called = True
                messages.append({
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in msg.tool_calls
                    ],
                })
                writer = _get_writer()
                for tc in msg.tool_calls:
                    args = json.loads(tc.function.arguments)
                    tool_name = tc.function.name
                    tool_label = _TOOL_LABELS.get(tool_name, tool_name)
                    writer({
                        "type": "tool_call",
                        "tool": tool_name,
                        "label": tool_label,
                        "args": args,
                        "phase": "start",
                    })
                    logger.info("工具调用: %s | 参数: %s", tool_name, args)
                    if mcp_session is not None:
                        results = await mcp_session.call_tool(tool_name, args)
                    elif search_fn is not None:
                        results = await search_fn(args.get("query", context))
                    else:
                        results = []
                    logger.info("工具返回: %s | 结果数: %d", tool_name, len(results))
                    writer({
                        "type": "tool_call",
                        "tool": tool_name,
                        "label": tool_label,
                        "phase": "end",
                        "result_count": len(results),
                    })
                    used_results.extend(results)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": _format_search_results(results),
                    })
            else:
                text = (msg.content or "").strip()
                if not text:
                    break
                try:
                    parsed = _extract_json_obj(text)
                    return _TopicsOutput.model_validate(parsed).topics, used_results
                except Exception as exc:
                    logger.warning(
                        "generate_topics: LLM 输出格式异常（可能是工具调用 JSON），忽略并继续: %s | raw=%s",
                        exc,
                        text[:200],
                    )
                    break

        return [], used_results

    async def stream_article(
        self,
        selected_topic: str,
        context: str,
        search_results: list[dict] | None = None,
    ) -> AsyncIterator[str]:
        """流式生成文案：逐段 yield 文本增量；结束后上报真实 token 用量。

        仅产出 `response.output_text.delta`（正文），忽略模型的思考摘要增量。
        """
        prompt = get_prompt("article_writer")
        system = prompt["system"].strip()
        user = prompt["user_template"].format(
            selected_topic=selected_topic,
            context=context,
            search_results=_format_search_results(search_results or []),
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
        text = await self._complete_json("image_prompt_extractor", draft_article=draft_article)
        return _PromptsOutput.model_validate(_extract_json_obj(text)).prompts

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
