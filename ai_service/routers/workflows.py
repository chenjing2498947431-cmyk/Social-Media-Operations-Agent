"""AI 工作流 HTTP 接口。

只暴露与图执行相关的薄接口，业务逻辑（campaign 落库等）放在 backend_api 处理。
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Path
from fastapi.responses import StreamingResponse
from langgraph.types import Command

from ai_service.graph.builder import get_graph
from shared_libs.schemas import (
    WorkflowResumeRequest,
    WorkflowStartRequest,
    WorkflowStateResponse,
    WorkflowStage,
)

router = APIRouter(prefix="/ai/v1/workflows", tags=["workflows"])


_THREAD_ID = Path(
    ...,
    description="LangGraph 的 thread_id，对应一次完整任务的会话",
    examples=["thread-demo-001"],
)


def _thread_config(thread_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id}}


def _sse(payload: dict[str, Any]) -> str:
    """打包成一条 SSE 消息（单 data 行）。"""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _classify_stage(state_values: dict[str, Any], interrupt_info: dict | None) -> WorkflowStage:
    if interrupt_info is None:
        if state_values.get("status") == "completed":
            return WorkflowStage.COMPLETED
        if state_values.get("status") == "failed":
            return WorkflowStage.FAILED
        return WorkflowStage.RUNNING

    action = interrupt_info.get("action")
    if action == "select_topic":
        return WorkflowStage.AWAITING_TOPIC
    if action == "review_article":
        return WorkflowStage.AWAITING_REVIEW
    return WorkflowStage.RUNNING


async def _build_state_response(thread_id: str) -> WorkflowStateResponse:
    graph = get_graph()
    snapshot = await graph.aget_state(_thread_config(thread_id))
    if snapshot is None:
        raise HTTPException(status_code=404, detail="thread not found")

    interrupt_info: dict | None = None
    # snapshot.tasks 里若有 task.interrupts，说明当前停在中断点
    for task in (snapshot.tasks or []):
        if task.interrupts:
            interrupt_info = task.interrupts[0].value
            break

    stage = _classify_stage(snapshot.values, interrupt_info)
    return WorkflowStateResponse(
        thread_id=thread_id,
        stage=stage,
        state=snapshot.values,
        interrupt=interrupt_info,
    )


@router.post(
    "",
    response_model=WorkflowStateResponse,
    summary="① 启动工作流",
    response_description=(
        "stage 通常为 `awaiting_topic`；"
        "interrupt 中携带 5 个 mock 备选选题"
    ),
    description=(
        "幂等：相同 `thread_id` 再次调用不会重启，仅返回当前 state。\n\n"
        "**调试建议**：thread_id 自己想一个，比如 `thread-demo-001`。"
    ),
)
async def start_workflow(req: WorkflowStartRequest) -> WorkflowStateResponse:
    graph = get_graph()
    initial_state = {
        "context": req.context,
        "topics": [],
        "image_prompts": [],
        "generated_images": [],
        "revision_round": 0,
        "status": "running",
        "node_metrics": [],
    }
    await graph.ainvoke(initial_state, config=_thread_config(req.thread_id))
    return await _build_state_response(req.thread_id)


@router.post(
    "/{thread_id}/resume",
    response_model=WorkflowStateResponse,
    summary="② / ③ 恢复中断（选题 or 审核）",
    response_description="返回恢复执行后的最新状态，可能再次停在新的中断点",
    description=(
        "根据当前 interrupt 类型，**payload 含义不同**：\n\n"
        "**当 stage=awaiting_topic（interrupt.action=select_topic）时：**\n"
        "```json\n"
        '{"payload": {"selected_topic": "【Mock】美联储议息会议背后的 A 股投资机会"}}\n'
        "```\n\n"
        "**当 stage=awaiting_review（interrupt.action=review_article）时：**\n"
        "- 通过：\n"
        "```json\n"
        '{"payload": {"decision": "approve"}}\n'
        "```\n"
        "- 拒绝并改写：\n"
        "```json\n"
        '{"payload": {"decision": "reject", "feedback": "请增加对黄金的论述"}}\n'
        "```\n"
    ),
)
async def resume_workflow(
    req: WorkflowResumeRequest,
    thread_id: str = _THREAD_ID,
) -> WorkflowStateResponse:
    graph = get_graph()
    snapshot = await graph.aget_state(_thread_config(thread_id))
    if snapshot is None:
        raise HTTPException(status_code=404, detail="thread not found")

    interrupt_info = None
    for task in (snapshot.tasks or []):
        if task.interrupts:
            interrupt_info = task.interrupts[0].value
            break

    if interrupt_info is None:
        raise HTTPException(status_code=409, detail="workflow is not interrupted")

    action = interrupt_info.get("action")
    payload = req.payload

    if action == "select_topic":
        selected = payload.get("selected_topic")
        if not selected:
            raise HTTPException(status_code=400, detail="selected_topic required")
        resume_value: Any = selected
    elif action == "review_article":
        decision = payload.get("decision")
        if decision not in ("approve", "reject"):
            raise HTTPException(status_code=400, detail="decision must be approve / reject")
        if decision == "reject" and not payload.get("feedback"):
            raise HTTPException(status_code=400, detail="feedback required when reject")
        resume_value = {
            "decision": decision,
            "feedback": payload.get("feedback"),
        }
    else:
        raise HTTPException(status_code=400, detail=f"unknown interrupt action: {action}")

    await graph.ainvoke(Command(resume=resume_value), config=_thread_config(thread_id))
    return await _build_state_response(thread_id)


@router.post(
    "/{thread_id}/resume/stream",
    summary="②/③（流式）恢复中断：实时回传节点运行过程与文案增量",
    response_description="text/event-stream：节点事件 + 文案增量，末尾返回完整工作流状态",
    description=(
        "流式版 `/resume`，**选题**与**审核**两种中断均支持。payload 同 `/resume`。\n\n"
        "SSE 事件（`data:` 行，JSON 含 `type`）：\n"
        "- `{\"type\":\"node\",\"node\":...,\"label\":...,\"phase\":\"start|end\"}`：节点开始/结束\n"
        "- `{\"type\":\"delta\",\"text\":...}`：文案文本增量\n"
        "- `{\"type\":\"state\",\"workflow_state\":{...}}`：完成后的完整状态\n"
        "- `{\"type\":\"error\",\"message\":...}`：异常"
    ),
)
async def resume_workflow_stream(
    req: WorkflowResumeRequest,
    thread_id: str = _THREAD_ID,
) -> StreamingResponse:
    graph = get_graph()
    snapshot = await graph.aget_state(_thread_config(thread_id))
    if snapshot is None:
        raise HTTPException(status_code=404, detail="thread not found")

    interrupt_info = None
    for task in (snapshot.tasks or []):
        if task.interrupts:
            interrupt_info = task.interrupts[0].value
            break
    if interrupt_info is None:
        raise HTTPException(status_code=409, detail="workflow is not interrupted")

    action = interrupt_info.get("action")
    payload = req.payload
    if action == "select_topic":
        selected = payload.get("selected_topic")
        if not selected:
            raise HTTPException(status_code=400, detail="selected_topic required")
        resume_value: Any = selected
    elif action == "review_article":
        decision = payload.get("decision")
        if decision not in ("approve", "reject"):
            raise HTTPException(
                status_code=400, detail="decision must be approve / reject"
            )
        if decision == "reject" and not payload.get("feedback"):
            raise HTTPException(status_code=400, detail="feedback required when reject")
        resume_value = {"decision": decision, "feedback": payload.get("feedback")}
    else:
        raise HTTPException(status_code=400, detail=f"unknown interrupt action: {action}")

    async def event_stream() -> Any:
        try:
            async for chunk in graph.astream(
                Command(resume=resume_value),
                config=_thread_config(thread_id),
                stream_mode="custom",
            ):
                # 节点生命周期 / 文案增量均由节点经 stream writer 推出
                if isinstance(chunk, dict) and chunk.get("type") in ("delta", "node"):
                    yield _sse(chunk)
            state_resp = await _build_state_response(thread_id)
            yield _sse(
                {"type": "state", "workflow_state": state_resp.model_dump(mode="json")}
            )
        except Exception as exc:  # noqa: BLE001
            yield _sse({"type": "error", "message": str(exc)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get(
    "/{thread_id}/state",
    response_model=WorkflowStateResponse,
    summary="查询工作流当前状态",
    description="任何时候都可以调用，前端轮询 / 刷新页面时用。",
)
async def get_workflow_state(thread_id: str = _THREAD_ID) -> WorkflowStateResponse:
    return await _build_state_response(thread_id)
