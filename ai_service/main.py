from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from ai_service.core.config import get_settings
from ai_service.persistence.checkpointer import close_checkpointer, init_checkpointer
from ai_service.graph.builder import reset_graph
from ai_service.routers.workflows import router as workflows_router

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


API_DESCRIPTION = """
**金融自媒体运营 Agent** - LangGraph 工作流服务。

直接驱动 LangGraph，便于跳过业务层做单图调试。手工跑通流程：

1. `POST /ai/v1/workflows` 启动 → 拿到 `interrupt.topics`
2. `POST /ai/v1/workflows/{thread_id}/resume`
   - payload: `{"selected_topic": "..."}` → 进入文案审核中断
3. 再次调 `/resume`
   - reject：`{"decision":"reject","feedback":"..."}` → revise 后再次停在审核
   - approve：`{"decision":"approve"}` → 出图 → stage=completed

随时 `GET /ai/v1/workflows/{thread_id}/state` 查看现状。

**业务侧推荐入口**：[http://localhost:8000/docs](http://localhost:8000/docs)。
"""


TAGS_METADATA = [
    {
        "name": "workflows",
        "description": "LangGraph 工作流薄接口：启动 / 恢复 / 查询。",
    },
    {"name": "health", "description": "探活。"},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    await init_checkpointer()
    reset_graph()
    logger.info(
        "ai_service ready  swagger: http://%s:%s/docs",
        settings.ai_service_host,
        settings.ai_service_port,
    )
    yield
    await close_checkpointer()
    print("ai_service进程已关闭")


app = FastAPI(
    title="Financial Agent · AI Service",
    version="0.1.0",
    description=API_DESCRIPTION,
    openapi_tags=TAGS_METADATA,
    lifespan=lifespan,
    swagger_ui_parameters={
        "docExpansion": "list",
        "defaultModelsExpandDepth": -1,
        "displayRequestDuration": True,
        "tryItOutEnabled": True,
        "persistAuthorization": True,
    },
)
app.include_router(workflows_router)


@app.get("/healthz", tags=["health"], summary="健康检查")
async def healthz():
    return {"ok": True, "service": "ai_service"}


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/docs")


if __name__ == "__main__":
    # 用 python -m ai_service.main 启动。
    # 包 __init__ 已把事件循环策略切到 SelectorEventLoop（psycopg async 必需）；
    # 这里直接 asyncio.run(Server.serve())，绕开 uvicorn.run() 内部会把策略改回
    # ProactorEventLoop 的 setup_event_loop()。
    import asyncio
    import uvicorn
    _settings = get_settings()
    _config = uvicorn.Config(
        app,
        host=_settings.ai_service_host,
        port=_settings.ai_service_port,
    )
    asyncio.run(uvicorn.Server(_config).serve())
