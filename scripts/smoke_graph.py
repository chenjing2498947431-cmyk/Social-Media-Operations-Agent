"""不启动 HTTP，直接驱动 LangGraph 走一遍完整流程，验证端到端真实调用 OK。
路径覆盖：
  1) 启动 -> 停在选题中断
  2) 提交选题 -> 停在审核中断
  3) reject + feedback -> 重写后再次停在审核中断
  4) approve -> 出图 -> END
"""
from __future__ import annotations

import asyncio
import json

from langgraph.types import Command

from ai_service.persistence.checkpointer import init_checkpointer
from ai_service.graph.builder import get_graph, reset_graph


def _dump(label: str, snapshot):
    interrupts = []
    for t in (snapshot.tasks or []):
        for itr in (t.interrupts or []):
            interrupts.append(itr.value)
    print(f"\n=== {label} ===")
    print("values:", json.dumps(snapshot.values, ensure_ascii=False, indent=2, default=str))
    if interrupts:
        print("interrupts:", json.dumps(interrupts, ensure_ascii=False, indent=2))
    print("next:", snapshot.next)


async def main():
    await init_checkpointer()
    reset_graph()
    graph = get_graph()

    cfg = {"configurable": {"thread_id": "smoke-thread-1"}}

    # Step 1: start
    await graph.ainvoke(
        {
            "context": "今日金融背景：美联储议息会议召开，A股震荡，黄金创新高",
            "topics": [],
            "image_prompts": [],
            "generated_images": [],
            "revision_round": 0,
            "status": "running",
            "node_metrics": [],
        },
        config=cfg,
    )
    snap = await graph.aget_state(cfg)
    _dump("after start (should await select_topic)", snap)
    assert any(t.interrupts for t in (snap.tasks or [])), "应停在选题中断"

    # Step 2: 提交选题
    await graph.ainvoke(Command(resume="【Mock】美联储议息会议背后的 A 股投资机会"), config=cfg)
    snap = await graph.aget_state(cfg)
    _dump("after select_topic (should await review)", snap)
    assert any(t.interrupts for t in (snap.tasks or [])), "应停在审核中断"

    # Step 3: reject + feedback -> revise -> 再次停在审核中断
    await graph.ainvoke(
        Command(resume={"decision": "reject", "feedback": "增加更多关于黄金的论述"}),
        config=cfg,
    )
    snap = await graph.aget_state(cfg)
    _dump("after reject (should still await review with new draft)", snap)
    assert snap.values.get("revision_round") == 1, "应该完成第一轮重写"
    assert any(t.interrupts for t in (snap.tasks or [])), "应再次停在审核中断"

    # Step 4: approve -> 跑到 END
    await graph.ainvoke(Command(resume={"decision": "approve"}), config=cfg)
    snap = await graph.aget_state(cfg)
    _dump("after approve (should END with images)", snap)
    assert snap.values.get("status") == "completed"
    assert snap.values.get("generated_images")
    assert not any(t.interrupts for t in (snap.tasks or []))

    print("\n[SMOKE OK] 端到端流程跑通")


if __name__ == "__main__":
    asyncio.run(main())
