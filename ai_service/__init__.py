"""ai_service 包初始化。

Windows 下 psycopg 的 async 模式无法运行在默认的 ProactorEventLoop 上，
必须在任何事件循环创建之前切换到 SelectorEventLoop。放在包 __init__ 里，
可保证只要 import 了 ai_service.*（如 main / smoke 脚本），策略就已生效。
"""
import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
