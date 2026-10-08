"""窗口重绘开关（Windows）。

Tk 在窗口缩放时会遍历所有可见控件重算几何并重绘，每增加一个控件就多约
0.6~1 ms，控件一多拖动就会发涩。拖动期间用 WM_SETREDRAW 暂停重绘，
停下来之后再整体刷新一次，可以把拖动过程中的开销压到很低。
"""

from __future__ import annotations

import ctypes
import sys

IS_WINDOWS = sys.platform == "win32"

WM_SETREDRAW = 0x000B
RDW_INVALIDATE = 0x0001
RDW_ERASE = 0x0004
RDW_ALLCHILDREN = 0x0080
RDW_UPDATENOW = 0x0100

_available = IS_WINDOWS


def available() -> bool:
    return _available


def window_handle(root) -> int:
    """取顶层窗口的 HWND。"""
    if not IS_WINDOWS:
        return 0
    try:
        return int(root.frame(), 16)
    except (ValueError, TypeError, AttributeError):
        try:
            return int(root.winfo_id())
        except Exception:  # noqa: BLE001
            return 0


def set_redraw(root, enabled: bool) -> bool:
    """开启或关闭窗口重绘；重新开启时立即整体刷新。"""
    if not IS_WINDOWS:
        return False
    handle = window_handle(root)
    if not handle:
        return False
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.SendMessageW.argtypes = [
            ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t
        ]
        user32.RedrawWindow.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint
        ]
        user32.SendMessageW(handle, WM_SETREDRAW, 1 if enabled else 0, 0)
        if enabled:
            user32.RedrawWindow(
                handle, None, None,
                RDW_INVALIDATE | RDW_ERASE | RDW_ALLCHILDREN | RDW_UPDATENOW,
            )
        return True
    except Exception:  # noqa: BLE001
        return False
