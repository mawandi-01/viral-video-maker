"""启动 Web 服务。

用法:
  cd /Users/ma/WorkBuddy/my-project
  source .venv/bin/activate
  python scripts/run_web.py
  或
  python scripts/run_web.py --port 8000 --reload
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> None:
    ap = argparse.ArgumentParser(description="run web server")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--reload", action="store_true")
    args = ap.parse_args()

    import uvicorn
    print(f"\n=== 爆款视频采集系统 ===")
    print(f"访问: http://localhost:{args.port}")
    print(f"API 文档: http://localhost:{args.port}/docs")
    print(f"按 Ctrl+C 停止\n")

    uvicorn.run(
        "src.web.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
