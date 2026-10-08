"""开机自启：Windows 注册表 Run 键 / macOS LaunchAgent / Linux autostart。"""

from __future__ import annotations

import shlex
import sys
from pathlib import Path

from ..config import APP_NAME, CONFIG_DIR

IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

WIN_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
WIN_VALUE_NAME = "LiteTools"
MAC_PLIST = Path.home() / "Library" / "LaunchAgents" / "com.litetools.app.plist"
LINUX_DESKTOP = Path.home() / ".config" / "autostart" / "litetools.desktop"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def launch_target() -> list[str]:
    """返回启动本程序所需的完整命令参数列表。"""
    if getattr(sys, "frozen", False):  # PyInstaller 打包后
        return [sys.executable, "--minimized"]
    script = _project_root() / "main.py"
    executable = sys.executable
    if IS_WINDOWS:
        windowed = Path(executable).with_name("pythonw.exe")
        if windowed.exists():
            executable = str(windowed)
    return [executable, str(script), "--minimized"]


def command_line() -> str:
    return subprocess_list_to_string(launch_target())


def subprocess_list_to_string(args: list[str]) -> str:
    return " ".join(f'"{a}"' if " " in a else a for a in args)


# ------------------------------------------------------------------ 状态
def is_enabled() -> bool:
    if IS_WINDOWS:
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WIN_RUN_KEY) as key:
                winreg.QueryValueEx(key, WIN_VALUE_NAME)
            return True
        except OSError:
            return False
    if IS_MAC:
        return MAC_PLIST.exists()
    return LINUX_DESKTOP.exists()


def current_target() -> str:
    """返回注册表中已写入的启动命令。"""
    if IS_WINDOWS:
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WIN_RUN_KEY) as key:
                return str(winreg.QueryValueEx(key, WIN_VALUE_NAME)[0])
        except OSError:
            return ""
    if IS_MAC:
        if not MAC_PLIST.exists():
            return ""
        return MAC_PLIST.read_text(encoding="utf-8")
    if LINUX_DESKTOP.exists():
        return LINUX_DESKTOP.read_text(encoding="utf-8")
    return ""


# ------------------------------------------------------------------ 开关
def enable() -> tuple[bool, str]:
    try:
        if IS_WINDOWS:
            return _enable_windows()
        if IS_MAC:
            return _enable_mac()
        return _enable_linux()
    except Exception as exc:  # noqa: BLE001
        return False, f"设置失败：{exc}"


def disable() -> tuple[bool, str]:
    try:
        if IS_WINDOWS:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WIN_RUN_KEY, 0,
                                winreg.KEY_SET_VALUE) as key:
                try:
                    winreg.DeleteValue(key, WIN_VALUE_NAME)
                except OSError:
                    pass
            return True, "已关闭开机自启"
        if IS_MAC:
            MAC_PLIST.unlink(missing_ok=True)
            return True, "已关闭开机自启"
        LINUX_DESKTOP.unlink(missing_ok=True)
        return True, "已关闭开机自启"
    except Exception as exc:  # noqa: BLE001
        return False, f"取消失败：{exc}"


def _enable_windows() -> tuple[bool, str]:
    import winreg

    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, WIN_RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, WIN_VALUE_NAME, 0, winreg.REG_SZ, command_line())
    return True, "已设置开机自启"


def _enable_mac() -> tuple[bool, str]:
    import subprocess

    args = [a for a in launch_target() if a != "--minimized"]
    program_args = "\n".join(f"        <string>{a}</string>" for a in args)
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.litetools.app</string>
    <key>ProgramArguments</key>
    <array>
{program_args}
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
"""
    MAC_PLIST.parent.mkdir(parents=True, exist_ok=True)
    MAC_PLIST.write_text(plist, encoding="utf-8")
    subprocess.run(["launchctl", "load", str(MAC_PLIST)], capture_output=True, check=False)
    return True, "已设置开机自启"


def _enable_linux() -> tuple[bool, str]:
    args = launch_target()
    exec_line = " ".join(_desktop_escape(a) for a in args)
    desktop = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={APP_NAME}\n"
        "Comment=Lite developer toolbox\n"
        f"Exec={exec_line}\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n"
    )
    LINUX_DESKTOP.parent.mkdir(parents=True, exist_ok=True)
    LINUX_DESKTOP.write_text(desktop, encoding="utf-8")
    return True, "已设置开机自启"


def _desktop_escape(value: str) -> str:
    if any(ch in value for ch in ' \t"'):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return value


def describe() -> str:
    """给设置页展示的说明文本。"""
    target = launch_target()
    if IS_WINDOWS:
        return f"注册表 HKCU\\{WIN_RUN_KEY}\\{WIN_VALUE_NAME}\n命令：{command_line()}"
    if IS_MAC:
        return f"LaunchAgent：{MAC_PLIST}\n命令：{shlex.join(target)}"
    return f"autostart：{LINUX_DESKTOP}\n命令：{shlex.join(target)}"


CONFIG_DIR.mkdir(parents=True, exist_ok=True)
