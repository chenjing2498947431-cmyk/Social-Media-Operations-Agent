from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from backend_api.core.config import get_settings
from backend_api.core.database import close_db, init_db
from backend_api.routers.campaigns import router as campaigns_router
from backend_api.routers.health import router as health_router

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


API_DESCRIPTION = """
**金融自媒体运营 Agent** - 业务后台服务。

按下面三步即可在 Swagger UI 上手工跑通整条工作流：

1. **创建任务** `POST /api/v1/campaigns`
   - body 示例已预填，点 *Try it out* → *Execute*。
   - 在返回 JSON 里复制 `id`（campaign_id）。
   - 在 `workflow_state.interrupt.topics` 里挑一个选题文本。

2. **提交选题** `POST /api/v1/campaigns/{id}/select-topic`
   - URL 里填上一步拿到的 `id`，body 里粘贴选题。
   - 返回的 `workflow_state.interrupt.draft_article` 就是 mock 草稿。

3. **审核** `POST /api/v1/campaigns/{id}/review-article`
   - 先用 `{"decision": "reject", "feedback": "..."}` 触发改写循环，
     之后 `revision_round` 会 +1，再调一次即可。
   - 最后用 `{"decision": "approve"}` 走到 `status=completed`，
     `state.generated_images` 即最终图片 URL。

如果想跳过业务层，直接调 LangGraph 的薄接口，请打开 AI Service 的 docs：
[http://localhost:8100/docs](http://localhost:8100/docs)。
"""


TAGS_METADATA = [
    {
        "name": "campaigns",
        "description": "Campaign（一次完整运营任务）的 CRUD + 工作流推进，调试主入口。",
    },
    {"name": "health", "description": "探活与基础信息。"},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    await init_db()
    logger.info(
        "backend_api ready  swagger: http://%s:%s/docs",
        settings.backend_api_host,
        settings.backend_api_port,
    )
    yield
    await close_db()


app = FastAPI(
    title="Financial Agent · Backend API",
    version="0.1.0",
    description=API_DESCRIPTION,
    openapi_tags=TAGS_METADATA,
    lifespan=lifespan,
    swagger_ui_parameters={
        "docExpansion": "list",   # 默认折叠到 operation 级别
        "defaultModelsExpandDepth": -1,  # 不展示底部 Schemas，专心调接口
        "displayRequestDuration": True,
        "tryItOutEnabled": True,
        "persistAuthorization": True,
    },
)
# 允许前端跨域访问。本应用无 Cookie 鉴权，故 allow_credentials=False，
# 这样即便 allow_origins=["*"] 也符合 CORS 规范。
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_allow_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(campaigns_router)


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/docs")
