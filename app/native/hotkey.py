"""全局快捷键。

Windows 下用 ctypes 直接调用 RegisterHotKey / GetMessageW，不依赖第三方库。
其它平台暂不支持（返回明确原因）。
"""

from __future__ import annotations

import ctypes
import sys
import threading
from typing import Callable

IS_WINDOWS = sys.platform == "win32"

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
HOTKEY_ID = 0xA17E

MODIFIER_ALIASES = {
    "ctrl": MOD_CONTROL,
    "control": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
    "win": MOD_WIN,
    "super": MOD_WIN,
    "cmd": MOD_WIN,
    "command": MOD_WIN,
}

_KEY_ALIASES = {
    "space": 0x20,
    "空格": 0x20,
    "enter": 0x0D,
    "return": 0x0D,
    "tab": 0x09,
    "esc": 0x1B,
    "escape": 0x1B,
    "backspace": 0x08,
    "insert": 0x2D,
    "delete": 0x2E,
    "del": 0x2E,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
    "`": 0xC0,
    "-": 0xBD,
    "=": 0xBB,
    "[": 0xDB,
    "]": 0xDD,
    "\\": 0xDC,
    ";": 0xBA,
    "'": 0xDE,
    ",": 0xBC,
    ".": 0xBE,
    "/": 0xBF,
}
for _i in range(1, 25):
    _KEY_ALIASES[f"f{_i}"] = 0x6F + _i


def normalize_key(text: str) -> str:
    """把界面输入规范化成配置里保存的形式。"""
    text = (text or "").strip()
    if not text:
        return ""
    lowered = text.lower()
    if lowered in _KEY_ALIASES:
        return lowered.upper() if lowered.startswith("f") and lowered[1:].isdigit() else lowered
    if len(text) == 1:
        return text.upper()
    return text


def describe(modifiers: list[str], key: str) -> str:
    names = {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "win": "Win"}
    parts = [names.get(m.lower(), m) for m in modifiers]
    if key:
        parts.append(key.upper() if len(key) == 1 else key)
    return " + ".join(parts) if parts else "未设置"


class GlobalHotkey:
    """在独立线程中接收 WM_HOTKEY。"""

    available = staticmethod(lambda: IS_WINDOWS)

    def __init__(self, callback: Callable[[], None]) -> None:
        self._callback = callback
        self._thread: threading.Thread | None = None
        self._thread_id: int = 0
        self._registered = False
        self._ready = threading.Event()
        self._result: tuple[bool, str] = (False, "")
        self._mods = 0
        self._vk = 0

    # ------------------------------------------------------------ 注册
    def apply(self, enabled: bool, modifiers: list[str], key: str) -> tuple[bool, str]:
        self.unregister()
        if not enabled:
            return True, "快捷键已关闭"
        if not IS_WINDOWS:
            return False, "当前系统暂不支持全局快捷键"
        mods = 0
        for name in modifiers or []:
            value = MODIFIER_ALIASES.get(str(name).lower())
            if value:
                mods |= value
        vk = _KEY_ALIASES.get(str(key).lower())
        if vk is None:
            if len(str(key)) == 1 and str(key).isalnum():
                vk = ord(str(key).upper())
            elif str(key).upper().startswith("F") and str(key)[1:].isdigit():
                index = int(str(key)[1:])
                vk = 0x6F + index if 1 <= index <= 24 else None
        if vk is None:
            return False, f"无法识别的按键：{key}"
        if mods == 0:
            return False, "至少需要选择一个修饰键（Ctrl / Alt / Shift / Win）"

        self._mods, self._vk = mods, vk
        self._ready.clear()
        self._result = (False, "注册超时")
        self._thread = threading.Thread(target=self._loop, daemon=True, name="hotkey")
        self._thread.start()
        self._ready.wait(timeout=3.0)
        return self._result

    def unregister(self) -> None:
        if self._registered and self._thread_id:
            try:
                user32 = ctypes.WinDLL("user32", use_last_error=True)
                user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            except OSError:
                pass
            if self._thread is not None:
                self._thread.join(timeout=2.0)
        self._registered = False
        self._thread = None
        self._thread_id = 0

    # ------------------------------------------------------------ 内部
    def _loop(self) -> None:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        user32.RegisterHotKey.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_uint
        ]
        user32.RegisterHotKey.restype = ctypes.c_bool
        user32.UnregisterHotKey.argtypes = [ctypes.c_void_p, ctypes.c_int]
        user32.GetMessageW.argtypes = [
            ctypes.POINTER(_Msg), ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint
        ]
        user32.GetMessageW.restype = ctypes.c_int
        user32.PostThreadMessageW.argtypes = [
            ctypes.c_uint, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t
        ]
        kernel32.GetCurrentThreadId.restype = ctypes.c_uint

        self._thread_id = int(kernel32.GetCurrentThreadId())
        ok = user32.RegisterHotKey(None, HOTKEY_ID, self._mods | MOD_NOREPEAT, self._vk)
        if not ok:
            self._result = (False, "热键已被其它程序占用，或组合无效")
            self._ready.set()
            return

        self._registered = True
        self._result = (True, "快捷键已生效")
        self._ready.set()

        message = _Msg()
        while True:
            ret = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
            if ret in (0, -1):
                break
            if message.message == WM_HOTKEY:
                try:
                    self._callback()
                except Exception:  # noqa: BLE001 - 回调异常不能杀死热键线程
                    pass

        user32.UnregisterHotKey(None, HOTKEY_ID)
        self._registered = False


class _Msg(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.c_void_p),
        ("message", ctypes.c_uint),
        ("wParam", ctypes.c_size_t),
        ("lParam", ctypes.c_ssize_t),
        ("time", ctypes.c_uint),
        ("pt_x", ctypes.c_long),
        ("pt_y", ctypes.c_long),
    ]
