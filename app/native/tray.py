"""系统托盘（Windows，基于 pywin32）。

托盘窗口跑在自己的线程里，所有回调通过队列交回主线程执行，避免跨线程操作 Tk。
"""

from __future__ import annotations

import queue
import sys
import threading
from pathlib import Path
from typing import Callable

IS_WINDOWS = sys.platform == "win32"

WM_TRAY = 0x0400 + 20  # WM_USER + 20

MENU_SHOW = 1001
MENU_QUIT = 1002


def available() -> tuple[bool, str]:
    if not IS_WINDOWS:
        return False, "托盘仅支持 Windows"
    try:
        import win32api  # noqa: F401
        import win32con  # noqa: F401
        import win32gui  # noqa: F401
    except ImportError:
        return False, "缺少 pywin32，无法启用托盘（pip install pywin32）"
    return True, "可用"


class TrayIcon:
    """系统托盘图标。回调在主线程（Tk 事件循环）中执行。"""

    def __init__(self, root, icon_path: Path | None, tooltip: str,
                 on_show: Callable[[], None], on_quit: Callable[[], None]) -> None:
        self._root = root
        self._icon_path = str(icon_path) if icon_path else ""
        self._tooltip = tooltip
        self._on_show = on_show
        self._on_quit = on_quit
        self._actions: "queue.Queue[str]" = queue.Queue()
        self._thread: threading.Thread | None = None
        self._hwnd = 0
        self._running = False
        self._error = ""
        self._pump_job: str | None = None
        # 托盘线程要一直跑消息循环，不能用 join 等它结束，只能等“就绪”信号
        self._ready = threading.Event()

    # ------------------------------------------------------------ 生命周期
    def start(self) -> bool:
        if self._running:
            return True
        self._thread = threading.Thread(target=self._run, daemon=True, name="tray")
        self._thread.start()
        self._ready.wait(timeout=3.0)
        if self._running:
            self._root.after(120, self._pump)
            return True
        return False

    def stop(self) -> None:
        self._running = False
        if self._pump_job is not None:
            try:
                self._root.after_cancel(self._pump_job)
            except Exception:  # noqa: BLE001 - 窗口已销毁
                pass
            self._pump_job = None
        if self._hwnd:
            try:
                import win32gui

                win32gui.PostMessage(self._hwnd, 0x0010, 0, 0)  # WM_CLOSE
            except Exception:  # noqa: BLE001
                pass

    @property
    def error(self) -> str:
        return self._error

    # ------------------------------------------------------------ 线程内部
    def _run(self) -> None:
        try:
            import win32api
            import win32con
            import win32gui
        except ImportError:
            self._error = "缺少 pywin32"
            self._ready.set()
            return

        def wnd_proc(hwnd, msg, wparam, lparam):
            if msg == WM_TRAY:
                if lparam == win32con.WM_RBUTTONUP:
                    self._show_menu(hwnd)
                elif lparam in (win32con.WM_LBUTTONUP, win32con.WM_LBUTTONDBLCLK):
                    self._actions.put("show")
            elif msg == win32con.WM_DESTROY:
                win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, (hwnd, 0))
                win32gui.PostQuitMessage(0)
            return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

        try:
            instance = win32api.GetModuleHandle(None)
            wc = win32gui.WNDCLASS()
            wc.hInstance = instance
            wc.lpszClassName = "LiteToolsTrayWindow"
            wc.lpfnWndProc = wnd_proc
            wc.hCursor = win32gui.LoadCursor(0, win32con.IDC_ARROW)
            class_atom = win32gui.RegisterClass(wc)
            hwnd = win32gui.CreateWindow(
                class_atom, "LiteToolsTray", win32con.WS_OVERLAPPED,
                0, 0, 0, 0, 0, 0, instance, None,
            )
            self._hwnd = hwnd
            hicon = self._load_icon()
            win32gui.Shell_NotifyIcon(
                win32gui.NIM_ADD,
                (hwnd, 0,
                 win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP,
                 WM_TRAY, hicon, self._tooltip),
            )
        except Exception as exc:  # noqa: BLE001
            self._error = str(exc)
            self._ready.set()
            return

        self._running = True
        self._ready.set()  # 通知主线程托盘已经可用
        win32gui.PumpMessages()
        self._running = False

    def _load_icon(self):
        import win32con
        import win32gui

        if self._icon_path and Path(self._icon_path).exists():
            try:
                return win32gui.LoadImage(
                    0, self._icon_path, win32con.IMAGE_ICON, 0, 0,
                    win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE,
                )
            except Exception:  # noqa: BLE001
                pass
        return win32gui.LoadIcon(0, win32con.IDI_APPLICATION)

    def _show_menu(self, hwnd: int) -> None:
        import win32con
        import win32gui

        menu = win32gui.CreatePopupMenu()
        win32gui.AppendMenu(menu, win32con.MF_STRING, MENU_SHOW, "显示主窗口")
        win32gui.AppendMenu(menu, win32con.MF_SEPARATOR, 0, "")
        win32gui.AppendMenu(menu, win32con.MF_STRING, MENU_QUIT, "退出")
        pos = win32gui.GetCursorPos()
        win32gui.SetForegroundWindow(hwnd)
        try:
            command = win32gui.TrackPopupMenu(
                menu, win32con.TPM_LEFTALIGN | win32con.TPM_RIGHTBUTTON,
                pos[0], pos[1], 0, hwnd, None,
            )
            win32gui.PostMessage(hwnd, win32con.WM_NULL, 0, 0)
        finally:
            win32gui.DestroyMenu(menu)
        if command == MENU_SHOW:
            self._actions.put("show")
        elif command == MENU_QUIT:
            self._actions.put("quit")

    # ------------------------------------------------------------ 主线程泵
    def _pump(self) -> None:
        self._pump_job = None
        try:
            while True:
                action = self._actions.get_nowait()
                if action == "show":
                    self._on_show()
                elif action == "quit":
                    self._on_quit()
        except queue.Empty:
            pass
        if self._running:
            try:
                self._pump_job = self._root.after(120, self._pump)
            except Exception:  # noqa: BLE001 - 窗口已销毁
                self._running = False
