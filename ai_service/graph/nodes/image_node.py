"""Node F & Node G：提炼图片文案 + 调用绘图 API。"""
from __future__ import annotations

from ai_service.core.metrics import track_node
from ai_service.graph.state import AgentState
from ai_service.tools.llm_client import get_llm_client
from ai_service.tools.image_gen_api import get_image_api


@track_node("extract_image_content")
async def extract_image_content(state: AgentState) -> dict:
    llm = get_llm_client()
    prompts = await llm.extract_image_prompts(state.get("draft_article", ""))
    return {
        "image_prompts": prompts,
        "status": "running",
    }


@track_node("generate_images")
async def generate_images(state: AgentState) -> dict:
    image_api = get_image_api()
    urls = await image_api.generate(state.get("image_prompts", []))
    return {
        "generated_images": urls,
        "status": "running",
    }


@track_node("generate_xhs_copy")
async def generate_xhs_copy(state: AgentState) -> dict:
    """根据已审核长文生成小红书风格文案，写入 state.xhs_copy。"""
    llm = get_llm_client()
    copy_text = await llm.generate_xhs_copy(
        selected_topic=state.get("selected_topic", ""),
        draft_article=state.get("draft_article", ""),
    )
    return {
        "xhs_copy": copy_text,
        "status": "completed",
    }
