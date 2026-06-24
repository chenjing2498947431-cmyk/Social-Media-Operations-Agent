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
from ai_service.tools.shared_platform_client import SharedPlatformClient
from ai_service.tools.config_center_client import ConfigCenterClient
from ai_service.tools.prompt_registry_client import PromptRegistryClient

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


def _fallback_topics(context: str) -> list[str]:
    subject = " ".join((context or "").split()).strip()[:60] or "当前金融市场"
    return [
        f"{subject}：市场波动背后的资金信号",
        f"{subject}：普通投资者需要关注的三条主线",
        f"{subject}：对A股、港股与黄金的影响拆解",
        f"{subject}：政策预期与风险偏好的再平衡",
        f"{subject}：下一阶段可能出现的机会与风险",
    ]


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

_MODEL_POLICY_BY_PROMPT: dict[str, str] = {
    "article_writer": "finance_article_writer",
    "article_reviser": "finance_article_reviser",
    "topic_generator": "finance_topic_gen",
    "xhs_copy_writer": "finance_xhs_copy_writer",
    "image_prompt_extractor": "finance_image_prompt_json",
}

_TASK_TYPE_BY_PROMPT: dict[str, str] = {
    "article_writer": "article_writer",
    "article_reviser": "article_reviser",
    "topic_generator": "generate_topic",
    "xhs_copy_writer": "xhs_copy_writer",
    "image_prompt_extractor": "image_prompt_extractor",
}

_JSON_SCHEMA_BY_PROMPT: dict[str, dict] = {
    "image_prompt_extractor": {
        "type": "object",
        "required": ["prompts"],
        "properties": {
            "prompts": {"type": "array", "items": {"type": "string"}},
        },
    },
}


class LLMClient:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._client: AsyncOpenAI | None = None
        self._shared_client: SharedPlatformClient | None = None
        self._config_client: ConfigCenterClient | None = None
        self._prompt_client: PromptRegistryClient | None = None
        self._task_config_cache: dict[str, dict[str, Any]] = {}

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            if not self._settings.ark_api_key:
                raise RuntimeError("必须配置 ARK_API_KEY（见 .env）")
            self._client = AsyncOpenAI(
                base_url=self._settings.ark_base_url,
                api_key=self._settings.ark_api_key,
            )
        return self._client

    def _get_shared_client(self) -> SharedPlatformClient:
        if self._shared_client is None:
            self._shared_client = SharedPlatformClient(self._settings.shared_platform_base_url)
        return self._shared_client

    def _get_config_client(self) -> ConfigCenterClient:
        if self._config_client is None:
            self._config_client = ConfigCenterClient(
                self._settings.shared_platform_base_url
            )
        return self._config_client

    def _get_prompt_client(self) -> PromptRegistryClient:
        if self._prompt_client is None:
            self._prompt_client = PromptRegistryClient(
                self._settings.shared_platform_base_url
            )
        return self._prompt_client

    async def _get_task_config(self, prompt_name: str) -> dict[str, Any]:
        if prompt_name not in self._task_config_cache:
            self._task_config_cache[prompt_name] = await self._get_config_client().get_task_config(
                self._settings.shared_platform_project_id,
                self._settings.shared_platform_env,
                self._task_type_for_prompt(prompt_name),
            )
        return self._task_config_cache[prompt_name]

    async def _get_prompt(self, prompt_name: str, **fields: str) -> dict[str, str]:
        if self._settings.shared_platform_enabled:
            try:
                task_config = await self._get_task_config(prompt_name)
                return await self._get_prompt_client().get_prompt(
                    self._settings.shared_platform_project_id,
                    self._settings.shared_platform_env,
                    task_config.get("prompt_key") or prompt_name,
                    version=task_config.get("prompt_version"),
                    **fields,
                )
            except Exception:
                pass
        prompt = get_prompt(prompt_name)
        user = prompt["user_template"].format(**fields).strip()
        return {"system": prompt["system"].strip(), "user_template": user}

    async def _resolve_model_policy(self, prompt_name: str) -> str:
        fallback = _MODEL_POLICY_BY_PROMPT.get(prompt_name, "finance_high_quality")
        if not self._settings.shared_platform_enabled:
            return fallback
        try:
            config = await self._get_task_config(prompt_name)
            return config.get("model_policy_id", fallback)
        except Exception:
            return fallback

    def _shared_messages(self, system: str, user: str) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    def _model_policy_for_prompt(self, prompt_name: str) -> str:
        return _MODEL_POLICY_BY_PROMPT.get(prompt_name, "finance_high_quality")

    def _task_type_for_prompt(self, prompt_name: str) -> str:
        return _TASK_TYPE_BY_PROMPT.get(prompt_name, "generate_article")

    async def _complete_json(self, prompt_name: str, **fields: str) -> str:
        """加载 prompt 配置 -> 拼接 -> 以 JSON mode 调用 -> 返回 JSON 文本。"""
        prompt = await self._get_prompt(prompt_name, **fields)
        system = prompt["system"]
        user = prompt["user_template"]

        if self._settings.shared_platform_enabled:
            result = await self._get_shared_client().json_generate(
                project_id=self._settings.shared_platform_project_id,
                env=self._settings.shared_platform_env,
                task_type=self._task_type_for_prompt(prompt_name),
                model_policy_id=await self._resolve_model_policy(prompt_name),
                messages=self._shared_messages(system, user),
                json_schema=_JSON_SCHEMA_BY_PROMPT.get(prompt_name, {"type": "object"}),
            )
            record_token_usage(
                result.usage.get("prompt_tokens", 0),
                result.usage.get("completion_tokens", 0),
            )
            return json.dumps(result.json_content or _extract_json_obj(result.content), ensure_ascii=False)

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
        prompt = await self._get_prompt(prompt_name, **fields)
        system = prompt["system"]
        user = prompt["user_template"]

        if self._settings.shared_platform_enabled:
            result = await self._get_shared_client().generate(
                project_id=self._settings.shared_platform_project_id,
                env=self._settings.shared_platform_env,
                task_type=self._task_type_for_prompt(prompt_name),
                model_policy_id=await self._resolve_model_policy(prompt_name),
                messages=self._shared_messages(system, user),
            )
            record_token_usage(
                result.usage.get("prompt_tokens", 0),
                result.usage.get("completion_tokens", 0),
            )
            return result.content

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
        prompt = await self._get_prompt("topic_generator", context=context)
        system = prompt["system"]
        user = prompt["user_template"]

        messages: list[dict] = [{"role": "user", "content": user}]
        used_results: list[dict] = []
        tool_called = False  # only allow one search call per generation

        # Discover available tools: prefer mcp_session, fall back to search_fn shim
        if mcp_session is not None:
            fn_defs = await mcp_session.list_tools()
            tools = [{"type": "function", "function": fn} for fn in fn_defs]
        elif search_fn is not None:
            tools = [_SEARCH_NEWS_TOOL]
        else:
            tools = []

        if self._settings.shared_platform_enabled:
            try:
                return await self._generate_topics_shared(
                    system, messages, tools, used_results,
                    mcp_session, search_fn, context,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("共享平台生成选题失败，返回本地兜底选题: %s", exc)
                return _fallback_topics(context), used_results

        try:
            oai = self._get_client()
        except Exception as exc:  # noqa: BLE001
            logger.warning("初始化模型客户端失败，返回本地兜底选题: %s", exc)
            return _fallback_topics(context), used_results
        for _ in range(2):
            create_kwargs: dict = {
                "model": self._settings.ark_model,
                "messages": [{"role": "system", "content": system}] + messages,
            }
            # After a tool call, omit tools so the LLM must produce content
            if tools and not tool_called:
                create_kwargs["tools"] = tools
                create_kwargs["tool_choice"] = "required"

            try:
                response = await oai.chat.completions.create(**create_kwargs)
            except Exception as exc:  # noqa: BLE001
                logger.warning("模型生成选题失败，返回本地兜底选题: %s", exc)
                return _fallback_topics(context), used_results

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

    async def _generate_topics_shared(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict],
        used_results: list[dict],
        mcp_session: Any | None,
        search_fn: Callable | None,
        context: str,
    ) -> tuple[list[str], list[dict]]:
        model_policy_id = await self._resolve_model_policy("topic_generator")
        tool_called = False
        for _ in range(2):
            req_messages = [{"role": "system", "content": system}] + messages
            result = await self._get_shared_client().generate(
                project_id=self._settings.shared_platform_project_id,
                env=self._settings.shared_platform_env,
                task_type=self._task_type_for_prompt("topic_generator"),
                model_policy_id=model_policy_id,
                messages=req_messages,
                tools=tools if not tool_called else None,
                tool_choice="required" if (tools and not tool_called) else None,
            )
            record_token_usage(
                result.usage.get("prompt_tokens", 0),
                result.usage.get("completion_tokens", 0),
            )
            if result.tool_calls and not tool_called:
                tool_called = True
                messages.append({
                    "role": "assistant",
                    "content": result.content or "",
                    "tool_calls": result.tool_calls,
                })
                writer = _get_writer()
                for tc in result.tool_calls:
                    args = json.loads(tc["function"]["arguments"])
                    tool_name = tc["function"]["name"]
                    tool_label = _TOOL_LABELS.get(tool_name, tool_name)
                    writer({
                        "type": "tool_call",
                        "tool": tool_name,
                        "label": tool_label,
                        "args": args,
                        "phase": "start",
                    })
                    logger.info("工具调用(shared): %s | 参数: %s", tool_name, args)
                    if mcp_session is not None:
                        results = await mcp_session.call_tool(tool_name, args)
                    elif search_fn is not None:
                        results = await search_fn(args.get("query", context))
                    else:
                        results = []
                    logger.info("工具返回(shared): %s | 结果数: %d", tool_name, len(results))
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
                        "tool_call_id": tc["id"],
                        "content": _format_search_results(results),
                    })
            else:
                text = (result.content or "").strip()
                if not text:
                    break
                try:
                    parsed = _extract_json_obj(text)
                    return _TopicsOutput.model_validate(parsed).topics, used_results
                except Exception as exc:
                    logger.warning(
                        "generate_topics(shared): LLM 输出格式异常: %s | raw=%s",
                        exc, text[:200],
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
        TODO(shared-platform): 等共享平台提供真实 SSE 后，再把本路径切到 LLM Gateway。
        """
        prompt = await self._get_prompt(
            "article_writer",
            selected_topic=selected_topic,
            context=context,
            search_results=_format_search_results(search_results or []),
        )
        system = prompt["system"]
        user = prompt["user_template"]

        if self._settings.shared_platform_enabled:
            shared_rag_results = await self._shared_rag_results(selected_topic)
            if shared_rag_results:
                merged_results = (search_results or []) + shared_rag_results
                prompt = await self._get_prompt(
                    "article_writer",
                    selected_topic=selected_topic,
                    context=context,
                    search_results=_format_search_results(merged_results),
                )
                system = prompt["system"]
                user = prompt["user_template"]
            async for chunk in self._get_shared_client().stream_generate(
                project_id=self._settings.shared_platform_project_id,
                env=self._settings.shared_platform_env,
                task_type=self._task_type_for_prompt("article_writer"),
                model_policy_id=await self._resolve_model_policy("article_writer"),
                messages=self._shared_messages(system, user),
            ):
                yield chunk
            return

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

    async def _shared_rag_results(self, query: str) -> list[dict]:
        try:
            return await self._get_shared_client().search_rag(
                project_id=self._settings.shared_platform_project_id,
                env=self._settings.shared_platform_env,
                kb_ids=["finance_news_rag"],
                query=query,
                top_k=5,
            )
        except Exception:
            return []

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
