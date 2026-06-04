"""一键启动所有服务（单终端，带彩色前缀日志）。

用法（在 financial_agent_project/ 目录下）：
    python start_all.py

Ctrl+C 停止全部服务。
"""
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.request import urlopen
from urllib.error import URLError

ROOT     = Path(__file__).parent
PYTHON   = r"D:\Anaconda3\envs\langchain\python.exe"
FRONTEND = ROOT / "frontend"

# ANSI 颜色（Windows Terminal / VSCode 终端均支持）
_C = {
    "MCP":      "\033[36m",   # 青
    "AI":       "\033[35m",   # 紫
    "Backend":  "\033[33m",   # 黄
    "Frontend": "\033[32m",   # 绿
}
_RESET = "\033[0m"
def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip()
    return env


def free_ports(*ports: int) -> None:
    result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
    for line in result.stdout.splitlines():
        for port in ports:
            if f":{port} " in line and "LISTENING" in line:
                pid = line.split()[-1]
                subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
                print(f"  释放端口 {port}（PID {pid}）")


def _pipe(proc: subprocess.Popen, label: str) -> None:
    """把子进程 stdout 逐行打印到当前终端，加彩色服务名前缀。"""
    color = _C.get(label, "")
    for raw in proc.stdout:  # type: ignore[union-attr]
        text = raw.decode("utf-8", errors="replace").rstrip()
        if text:
            print(f"{color}[{label}]{_RESET} {text}", flush=True)


def start(label: str, cmd, **kwargs) -> subprocess.Popen:
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        **kwargs,
    )
    threading.Thread(target=_pipe, args=(proc, label), daemon=True).start()
    return proc


def wait_healthy(url: str, retries: int = 10, interval: int = 3) -> bool:
    for _ in range(retries):
        try:
            with urlopen(url, timeout=3) as r:
                if r.status < 400:
                    return True
        except (URLError, OSError):
            pass
        time.sleep(interval)
    return False


def main() -> None:
    env = load_env()
    brave_key = env.get("BRAVE_API_KEY", "")

    print(">>> 清理端口 5173 / 8000 / 8100 / 8200 ...")
    free_ports(5173, 8000, 8100, 8200)
    time.sleep(1)

    procs: list[subprocess.Popen] = []

    print(">>> [MCP]      Brave MCP Server  (port 8200)")
    procs.append(start(
        "MCP",
        "npx -y @brave/brave-search-mcp-server --transport http --port 8200",
        env={**os.environ, "BRAVE_API_KEY": brave_key},
        shell=True, cwd=str(ROOT),
    ))
    time.sleep(5)

    print(">>> [AI]       AI Service         (port 8100)")
    procs.append(start(
        "AI",
        [PYTHON, "-m", "ai_service.main"],
        cwd=str(ROOT),
    ))
    time.sleep(3)

    print(">>> [Backend]  Backend API        (port 8000)")
    procs.append(start(
        "Backend",
        [PYTHON, "-m", "uvicorn", "backend_api.main:app",
         "--host", "0.0.0.0", "--port", "8000", "--reload"],
        cwd=str(ROOT),
    ))
    time.sleep(2)

    print(">>> [Frontend] Frontend           (port 5173)")
    procs.append(start(
        "Frontend",
        "npm run dev",
        shell=True, cwd=str(FRONTEND),
    ))

    print("\n>>> 等待服务就绪（最多 30 秒）...")
    time.sleep(8)
    for name, url in [
        ("AI Service ", "http://localhost:8100/healthz"),
        ("Backend API", "http://localhost:8000/healthz"),
    ]:
        ok = wait_healthy(url)
        print(f"  {name}: {'✓ OK' if ok else '未响应（可能仍在启动）'}")

    print("\n=====================================")
    print("  Frontend   ->  http://localhost:5173")
    print("  Backend    ->  http://localhost:8000/docs")
    print("  AI Service ->  http://localhost:8100/docs")
    print("  按 Ctrl+C 停止所有服务")
    print("=====================================\n")

    try:
        while True:
            for p in procs:
                if p.poll() is not None:
                    print("\n[!] 某个服务意外退出，停止全部...")
                    raise KeyboardInterrupt
            time.sleep(2)
    except KeyboardInterrupt:
        print("\n>>> 正在停止所有服务...")
        for p in procs:
            p.terminate()
        time.sleep(1)
        print(">>> 已全部停止。")


if __name__ == "__main__":
    main()
