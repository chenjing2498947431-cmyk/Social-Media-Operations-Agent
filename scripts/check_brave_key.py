"""验证 Brave Search API Key 是否有效。

直接调 Brave REST API（绕过 MCP Server），明确区分三种失败原因：
  - key 无效 / 未授权 (401)
  - 配额耗尽 (429)
  - 网络/其他问题

用法：
    python -m scripts.check_brave_key
    # 或指定 key：
    python -m scripts.check_brave_key --key <YOUR_KEY>
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

# 加载项目根目录的 .env
_ROOT = Path(__file__).parent.parent
load_dotenv(_ROOT / ".env")

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
TEST_QUERY = "美联储利率"


async def check(api_key: str) -> None:
    print(f"API Key : {api_key[:8]}{'*' * (len(api_key) - 8)}")
    print(f"Endpoint: {BRAVE_SEARCH_URL}")
    print(f"Query   : {TEST_QUERY!r}")
    print("-" * 50)

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            BRAVE_SEARCH_URL,
            params={"q": TEST_QUERY, "count": 3},
            headers={
                "X-Subscription-Token": api_key,
                "Accept": "application/json",
            },
        )

    status = resp.status_code
    if status == 200:
        data = resp.json()
        results = data.get("web", {}).get("results", [])
        print(f"[OK] Key 有效，返回 {len(results)} 条结果")
        for i, r in enumerate(results, 1):
            print(f"  {i}. {r.get('title', '')} — {r.get('url', '')[:60]}")
    elif status == 401:
        print("[FAIL] 401 Unauthorized — Key 无效或未激活，请到 https://brave.com/search/api/ 确认")
        sys.exit(1)
    elif status == 403:
        print("[FAIL] 403 Forbidden — Key 没有 Web Search 权限，检查订阅套餐")
        sys.exit(1)
    elif status == 429:
        print("[FAIL] 429 Too Many Requests — 配额已耗尽，等明天重置或升级套餐")
        sys.exit(1)
    else:
        print(f"[FAIL] HTTP {status} — {resp.text[:200]}")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="验证 Brave Search API Key")
    parser.add_argument("--key", default=None, help="指定 key（默认读 .env 中的 BRAVE_API_KEY）")
    args = parser.parse_args()

    api_key = args.key or os.getenv("BRAVE_API_KEY", "")
    if not api_key:
        print("[ERROR] 未找到 BRAVE_API_KEY，请在 .env 中配置或用 --key 参数传入")
        sys.exit(1)

    asyncio.run(check(api_key))


if __name__ == "__main__":
    main()
