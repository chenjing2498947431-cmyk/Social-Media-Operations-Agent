from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get(
    "/healthz",
    summary="健康检查",
    description="探活端点，返回 `{ok: true, service: 'backend_api'}`。",
)
async def healthz():
    return {"ok": True, "service": "backend_api"}
