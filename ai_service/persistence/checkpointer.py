"""LangGraph v1.x Checkpointer 选择器：
- 当配置了 LANGGRAPH_CHECKPOINT_DSN 时，使用 AsyncPostgresSaver
- 否则 fallback 到 InMemorySaver（便于本地 mock 验证）

LangGraph 1.0 起 `MemorySaver` 已重命名为 `InMemorySaver`，本文件优先用新名字，
若安装的次版本仍只暴露旧名字则回退到 `MemorySaver`。
"""
from __future__ import annotations

import logging

from ai_service.core.config import get_settings

logger = logging.getLogger(__name__)

try:
    from langgraph.checkpoint.memory import InMemorySaver as _InMemoryCheckpointer
except ImportError:  # 兼容个别 1.x 版本
    from langgraph.checkpoint.memory import MemorySaver as _InMemoryCheckpointer  # type: ignore


_checkpointer = None
_pg_pool_cm = None  # 持有 AsyncPostgresSaver 的 async context manager（避免被 GC）


async def init_checkpointer():
    """在 FastAPI startup 时调用。"""
    global _checkpointer, _pg_pool_cm
    if _checkpointer is not None:
        return _checkpointer

    settings = get_settings()
    dsn = settings.langgraph_checkpoint_dsn

    if dsn:
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
            _pg_pool_cm = AsyncPostgresSaver.from_conn_string(dsn)
            saver = await _pg_pool_cm.__aenter__()
            await saver.setup()
            _checkpointer = saver
            logger.info("LangGraph 使用 AsyncPostgresSaver: %s", dsn)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "AsyncPostgresSaver 初始化失败，fallback 到 InMemorySaver: %s", exc
            )
            _checkpointer = _InMemoryCheckpointer()
    else:
        logger.info("未配置 LANGGRAPH_CHECKPOINT_DSN，使用 InMemorySaver")
        _checkpointer = _InMemoryCheckpointer()

    return _checkpointer


async def close_checkpointer():
    global _checkpointer, _pg_pool_cm
    if _pg_pool_cm is not None:
        try:
            await _pg_pool_cm.__aexit__(None, None, None)
        except Exception:  # noqa: BLE001
            pass
    _pg_pool_cm = None
    _checkpointer = None


def get_checkpointer():
    if _checkpointer is None:
        raise RuntimeError("Checkpointer 尚未初始化，应用启动时需调用 init_checkpointer()")
    return _checkpointer
