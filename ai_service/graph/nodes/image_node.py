"""Node F & Node G：提炼图片文案 + 调用绘图 API。"""
from __future__ import annotations

from ai_service.graph.state import AgentState
from ai_service.tools.llm_client import get_llm_client
from ai_service.tools.image_gen_api import get_image_api


async def extract_image_content(state: AgentState) -> dict:
    llm = get_llm_client()
    prompts = await llm.extract_image_prompts(state.get("draft_article", ""))
    return {
        "image_prompts": prompts,
        "status": "running",
    }


async def generate_images(state: AgentState) -> dict:
    image_api = get_image_api()
    urls = await image_api.generate(state.get("image_prompts", []))
    return {
        "generated_images": urls,
        "status": "completed",
    }
