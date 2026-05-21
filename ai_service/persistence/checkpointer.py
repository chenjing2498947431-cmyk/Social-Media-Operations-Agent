"""LangGraph v1.x Checkpointer 选择器：
- 当配置了 LANGGRAPH_CHECKPOINT_DSN 时，使用 AsyncPostgresSaver；
  初始化失败会直接抛错（不再静默降级），以免数据未真正落库却无人察觉。
- 未配置 DSN 时使用 InMemorySaver（仅本地验证，进程重启即丢状态）。

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
            logger.info("LangGraph 使用 AsyncPostgresSaver")
        except Exception:
            logger.error(
                "AsyncPostgresSaver 初始化失败，请检查 LANGGRAPH_CHECKPOINT_DSN "
                "是否正确、数据库是否可达"
            )
            raise
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
