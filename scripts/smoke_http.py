"""HTTP 端到端联调：在子进程里启动 ai_service + backend_api，
通过 backend_api 暴露的接口走完整流程，再断言最终状态正确。
"""
from __future__ import annotations

import asyncio
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx


PROJECT_ROOT = Path(__file__).resolve().parents[1]
# 默认沿用当前解释器；外部可通过 PYTHON_EXEC 环境变量覆盖
PYTHON = os.environ.get("PYTHON_EXEC", sys.executable)
BACKEND_PORT = 8000
AI_PORT = 8100


def _wait_for(url: str, timeout: float = 30.0) -> None:
    start = time.time()
    while time.time() - start < timeout:
        try:
            with httpx.Client(timeout=2.0) as c:
                r = c.get(url)
                if r.status_code == 200:
                    return
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError(f"timeout waiting {url}")


def _free_db_file():
    db = PROJECT_ROOT / "backend.db"
    if db.exists():
        try:
            db.unlink()
        except Exception:
            pass


def _start(name: str, mod: str, port: int, env: dict) -> subprocess.Popen:
    print(f"[boot] starting {name} on :{port}")
    return subprocess.Popen(
        [PYTHON, "-m", "uvicorn", mod, "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=sys.stdout,
        stderr=sys.stderr,
    )


async def run_flow():
    base = f"http://127.0.0.1:{BACKEND_PORT}"
    async with httpx.AsyncClient(timeout=60.0, base_url=base) as c:
        # 1) 创建 campaign
        r = await c.post("/api/v1/campaigns", json={
            "context": "美联储议息会议召开，黄金创新高，A 股震荡",
            "title": "5月19日金融选题",
        })
        r.raise_for_status()
        camp = r.json()
        print("[step] created campaign:", camp["id"], "status=", camp["status"])
        assert camp["status"] == "pending_topic", camp
        assert camp["workflow_state"]["stage"] == "awaiting_topic"
        assert camp["workflow_state"]["interrupt"]["action"] == "select_topic"
        topics = camp["workflow_state"]["interrupt"]["topics"]
        assert len(topics) >= 3

        cid = camp["id"]

        # 2) 选定其中一个选题
        r = await c.post(f"/api/v1/campaigns/{cid}/select-topic", json={
            "selected_topic": topics[1],
        })
        r.raise_for_status()
        camp = r.json()
        print("[step] selected topic -> status=", camp["status"])
        assert camp["status"] == "pending_review"
        assert camp["workflow_state"]["interrupt"]["action"] == "review_article"
        assert camp["workflow_state"]["interrupt"]["revision_round"] == 0
        first_draft = camp["workflow_state"]["interrupt"]["draft_article"]
        assert "Mock" in first_draft

        # 3) 拒绝 + 反馈 -> 重写后再次停在审核
        r = await c.post(f"/api/v1/campaigns/{cid}/review-article", json={
            "decision": "reject",
            "feedback": "请增加对黄金避险逻辑的论证",
        })
        r.raise_for_status()
        camp = r.json()
        print("[step] rejected once -> status=", camp["status"])
        assert camp["status"] == "pending_review"
        assert camp["workflow_state"]["interrupt"]["revision_round"] == 1
        revised_draft = camp["workflow_state"]["interrupt"]["draft_article"]
        assert "修订" in revised_draft or "修订稿" in revised_draft or "Mock" in revised_draft
        assert revised_draft != first_draft

        # 4) 同意 -> END，应该有 image_prompts + generated_images
        r = await c.post(f"/api/v1/campaigns/{cid}/review-article", json={
            "decision": "approve",
        })
        r.raise_for_status()
        camp = r.json()
        print("[step] approved -> status=", camp["status"])
        assert camp["status"] == "completed", camp
        state = camp["workflow_state"]["state"]
        assert state["status"] == "completed"
        assert len(state["image_prompts"]) >= 3
        assert len(state["generated_images"]) >= 3
        print("[final] images:", state["generated_images"])

        # 5) 列表/详情可读
        r = await c.get("/api/v1/campaigns")
        r.raise_for_status()
        assert any(x["id"] == cid for x in r.json())
        r = await c.get(f"/api/v1/campaigns/{cid}")
        r.raise_for_status()
        print("[step] detail ok, status=", r.json()["status"])

    print("\n[HTTP SMOKE OK] 端到端 HTTP 流程跑通")


def main():
    _free_db_file()

    env_common = os.environ.copy()
    env_common["PYTHONPATH"] = str(PROJECT_ROOT)
    env_common["PYTHONIOENCODING"] = "utf-8"
    # 强制 MemorySaver，避免依赖 Postgres
    env_common["LANGGRAPH_CHECKPOINT_DSN"] = ""
    env_common["DATABASE_URL"] = "sqlite+aiosqlite:///./backend.db"
    env_common["AI_SERVICE_BASE_URL"] = f"http://127.0.0.1:{AI_PORT}"
    env_common["USE_MOCK_LLM"] = "true"
    env_common["USE_MOCK_IMAGE"] = "true"

    ai = _start("ai_service", "ai_service.main:app", AI_PORT, env_common)
    backend = _start("backend_api", "backend_api.main:app", BACKEND_PORT, env_common)

    try:
        _wait_for(f"http://127.0.0.1:{AI_PORT}/healthz")
        _wait_for(f"http://127.0.0.1:{BACKEND_PORT}/healthz")
        asyncio.run(run_flow())
    finally:
        for p in (backend, ai):
            try:
                if os.name == "nt":
                    p.send_signal(signal.CTRL_BREAK_EVENT if False else signal.SIGTERM)
                else:
                    p.terminate()
            except Exception:
                pass
        for p in (backend, ai):
            try:
                p.wait(timeout=5)
            except Exception:
                p.kill()


if __name__ == "__main__":
    main()
