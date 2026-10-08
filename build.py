#!/usr/bin/env python3
"""用 PyInstaller 打包。

用法：
    pip install pyinstaller
    python build.py            # 生成 dist/LiteTools/ 目录（推荐，启动最快）
    python build.py --onefile  # 生成单个 exe（便于分发，但每次启动都要解压）

关于启动速度：
    onefile 会把整个包压缩进一个 exe，每次运行时先解压到临时目录再启动，
    体积越大等待越久。onedir 没有这一步，启动明显更快，推荐日常使用。
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NAME = "LiteTools"

# 这些模块本项目完全用不到，排除掉可以减小体积、缩短启动时间。
# 只列确定安全的大块依赖，避免误伤被间接引用的标准库导致运行时报错。
EXCLUDES = (
    "numpy", "pandas", "scipy", "matplotlib", "PIL", "Pillow",
    "PyQt5", "PyQt6", "PySide2", "PySide6", "wx",
    "IPython", "jupyter", "notebook", "pytest",
    "tkinter.test", "test", "tests",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="打包 Lite Tools")
    parser.add_argument("--onefile", action="store_true",
                        help="生成单个 exe（便捷但启动需要解压）")
    parser.add_argument("--keep", action="store_true", help="保留上次的 build 缓存")
    parser.add_argument("--name", default=NAME, help=f"可执行文件名，默认 {NAME}")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("未安装 PyInstaller，请先执行：pip install pyinstaller")
        return 1

    command = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--windowed",          # 不弹控制台
        "--noupx",             # UPX 压缩会让每次启动都变慢
        "--name", args.name,
        "--paths", str(ROOT),
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build"),
        "--specpath", str(ROOT),
        "--onefile" if args.onefile else "--onedir",
    ]
    if not args.keep:
        command.append("--clean")

    # 托盘是可选依赖，静态分析可能漏掉
    if sys.platform == "win32":
        for module in ("win32api", "win32con", "win32gui"):
            command += ["--hidden-import", module]
    for module in EXCLUDES:
        command += ["--exclude-module", module]

    command.append(str(ROOT / "main.py"))

    print("执行：", " ".join(command))
    print()
    result = subprocess_run(command)
    if result != 0:
        return result

    dist = ROOT / "dist"
    if args.onefile:
        target = dist / (f"{args.name}.exe" if sys.platform == "win32" else args.name)
        if target.exists():
            print(f"\n打包完成：{target}  ({target.stat().st_size / 1024 / 1024:.1f} MB)")
        print("提示：单文件版每次启动都要先解压，如果嫌慢可以改用 python build.py 生成目录版。")
    else:
        folder = dist / args.name
        exe = folder / (f"{args.name}.exe" if sys.platform == "win32" else args.name)
        total = sum(f.stat().st_size for f in folder.rglob("*") if f.is_file()) if folder.exists() else 0
        print(f"\n打包完成：{folder}  (共 {total / 1024 / 1024:.1f} MB)")
        print(f"运行 {exe.name} 即可；整个目录可以直接拷贝到其它机器使用。")
    return 0


def subprocess_run(command: list[str]) -> int:
    import subprocess

    try:
        return subprocess.call(command)
    except KeyboardInterrupt:
        shutil.rmtree(ROOT / "build", ignore_errors=True)
        return 130


if __name__ == "__main__":
    sys.exit(main())
