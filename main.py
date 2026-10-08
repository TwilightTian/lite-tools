#!/usr/bin/env python3
"""Lite Tools —— 轻量跨平台开发小工具箱。

直接运行：python main.py
最小化启动：python main.py --minimized
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

MIN_PYTHON = (3, 9)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="LiteTools",
        description="开发小工具箱：JSON、时间戳、启动变量、代码生成、网络工具",
    )
    parser.add_argument("--minimized", action="store_true",
                        help="启动后直接隐藏到托盘（开机自启时使用）")
    parser.add_argument("--version", action="store_true", help="显示版本号并退出")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if sys.version_info < MIN_PYTHON:
        _warn(f"需要 Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} 及以上版本，当前为 {sys.version.split()[0]}")
        return 1

    from app.config import APP_VERSION, get_config
    from app.theme import enable_dpi_awareness

    if args.version:
        print(f"Lite Tools {APP_VERSION}")
        return 0

    # 必须在创建 Tk 根窗口之前开启，否则窗口会被系统位图拉伸导致文字发虚
    enable_dpi_awareness()

    try:
        from app.window import create
    except ImportError as exc:
        _warn(f"缺少依赖：{exc}\n如果是 Windows 且需要托盘功能，请执行：pip install pywin32")
        return 1

    config = get_config()
    window = create(start_minimized=args.minimized)
    _ = config
    window.run()
    return 0


def _warn(message: str) -> None:
    """兼容 pythonw.exe（无控制台）下的输出。"""
    try:
        sys.stderr.write(message + "\n")
    except Exception:  # noqa: BLE001
        pass


if __name__ == "__main__":
    sys.exit(main())
