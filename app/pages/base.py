"""页面基类：统一布局骨架、异步任务、忙碌状态与进度反馈。"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
import traceback
from typing import Any, Callable, Iterable, Sequence

from .. import theme
from ..core.json_utils import JsonError
from ..theme import PALETTE
from ..widgets import (
    Card,
    CodeText,
    ProgressLine,
    ScrollArea,
    add_context_menu,
    copy_to_clipboard,
)

_POLL_MS = 100


class Page(tk.Frame):
    """所有功能页面的基类。

    - 内容请放进 `self.body`；
    - 耗时操作一律用 `run_async` / `run_stream`，它们会负责禁用按钮并显示进度；
    - **不要**在工作线程里读取 Tk 变量，先把值取到局部变量再传进去。
    """

    title = ""
    desc = ""

    def __init__(self, master: tk.Misc, app) -> None:
        super().__init__(master, background=PALETTE["bg"])
        self.app = app
        self.config = app.config
        self._tasks: "queue.Queue[tuple[Callable | None, Any]]" = queue.Queue()
        self._polling = False
        self._busy_count = 0

        side = theme.sp(18)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        # 窗口太矮时整页可滚动，避免内容被裁掉
        self.scroll = ScrollArea(self, parent_bg=PALETTE["bg"])
        self.scroll.grid(row=0, column=0, sticky="nsew",
                         padx=side, pady=(theme.sp(14), theme.sp(6)))
        self.body = self.scroll.content
        self.body.columnconfigure(0, weight=1)
        self.body.rowconfigure(0, weight=1)

        self.progress = ProgressLine(self, parent_bg=PALETTE["bg"])
        self.progress.grid(row=1, column=0, sticky="ew", padx=side,
                           pady=(0, theme.sp(8)))
        self.progress.grid_remove()

        self._poll_job: str | None = None
        self.bind("<Destroy>", self._on_destroy)
        self.build()
        self._start_poll()

    def _on_destroy(self, event: tk.Event) -> None:
        """窗口销毁时停掉轮询，否则定时器会在控件消失后继续触发。"""
        if event.widget is not self:
            return
        self._polling = False
        if self._poll_job is not None:
            try:
                self.after_cancel(self._poll_job)
            except tk.TclError:
                pass
            self._poll_job = None

    # ------------------------------------------------------------ 生命周期
    def build(self) -> None:
        raise NotImplementedError

    def on_show(self) -> None:
        """页面被切到前台时调用。"""

    def on_hide(self) -> None:
        """页面被切走时调用。"""

    # ------------------------------------------------------------ 状态提示
    def status(self, text: str, kind: str = "info") -> None:
        self.app.set_status(text, kind)

    def copy(self, text: str, tip: str = "已复制到剪贴板") -> None:
        copy_to_clipboard(self.app.root, text)
        self.status(tip, "ok")

    def make_code_area(self, parent: tk.Misc, **kwargs) -> CodeText:
        area = CodeText(parent, **kwargs)
        add_context_menu(area.text)
        return area

    def run_guarded(self, action: Callable[[], None]) -> None:
        """同步执行并统一处理异常，避免弹窗打断操作。"""
        try:
            action()
        except JsonError as exc:
            self.status(f"JSON 错误：{exc}", "err")
        except ValueError as exc:
            self.status(str(exc), "err")
        except Exception as exc:  # noqa: BLE001
            self.status(f"{type(exc).__name__}：{exc}", "err")

    # ------------------------------------------------------------ 进度
    def show_progress(self, ratio: float | None = None) -> None:
        """显示进度条；ratio 为 None 时使用循环流动模式。"""
        self._busy_count += 1
        if self._busy_count == 1:
            self.progress.grid()
        if ratio is None:
            self.progress.start()
        else:
            self.progress.set(ratio)

    def update_progress(self, ratio: float) -> None:
        self.progress.set(ratio)

    def hide_progress(self) -> None:
        self._busy_count = max(0, self._busy_count - 1)
        if self._busy_count == 0:
            self.progress.stop()
            self.progress.grid_remove()

    # ------------------------------------------------------------ 异步
    def _start_poll(self) -> None:
        if not self._polling:
            self._polling = True
            self._poll_job = self.after(_POLL_MS, self._poll)

    def _poll(self) -> None:
        try:
            while True:
                handler, payload = self._tasks.get_nowait()
                if handler is not None:
                    try:
                        handler(payload)
                    except tk.TclError:
                        pass  # 窗口已销毁
                    except Exception:  # noqa: BLE001
                        traceback.print_exc()
        except queue.Empty:
            pass
        if self._polling:
            self._poll_job = self.after(_POLL_MS, self._poll)

    @staticmethod
    def _set_enabled(widgets: Sequence[tk.Widget], enabled: bool) -> None:
        for widget in widgets:
            if widget is None:
                continue
            try:
                if hasattr(widget, "set_enabled"):
                    widget.set_enabled(enabled)
                else:
                    widget.configure(state="normal" if enabled else "disabled")
            except tk.TclError:
                pass

    def _make_release(self, busy: Sequence[tk.Widget], progress: bool) -> Callable:
        widgets = [w for w in busy if w is not None]

        def release(_payload: Any = None) -> None:
            self._set_enabled(widgets, True)
            if progress:
                self.hide_progress()

        return release

    def run_async(self, work: Callable[[], Any],
                  on_success: Callable[[Any], None] | None = None,
                  on_error: Callable[[Exception], None] | None = None,
                  busy: Sequence[tk.Widget] = (),
                  progress: bool = False) -> None:
        """后台执行 `work()`，主线程回调结果。

        busy 中的控件会在任务期间禁用，避免重复点击；
        progress 为真时显示循环进度条。
        """
        release = self._make_release(busy, progress)
        self._set_enabled([w for w in busy if w is not None], False)
        if progress:
            self.show_progress()

        def worker() -> None:
            try:
                result = work()
            except Exception as exc:  # noqa: BLE001
                self._tasks.put((on_error or self._default_error, exc))
            else:
                self._tasks.put((on_success, result))
            finally:
                self._tasks.put((release, None))

        threading.Thread(target=worker, daemon=True).start()

    def run_stream(self, stream: Iterable[Any], on_line: Callable[[Any], None],
                   on_success: Callable[[Any], None] | None = None,
                   on_error: Callable[[Exception], None] | None = None,
                   busy: Sequence[tk.Widget] = (),
                   progress: bool = False,
                   total: int | None = None) -> None:
        """逐条消费 `stream`，每条在主线程交给 `on_line`。

        total 给定时进度条按条数推进，否则使用循环模式。
        """
        release = self._make_release(busy, progress)
        self._set_enabled([w for w in busy if w is not None], False)
        if progress:
            self.show_progress(0.0 if total else None)

        done = 0

        def worker() -> None:
            nonlocal done
            try:
                for item in stream:
                    done += 1
                    self._tasks.put((on_line, item))
                    if progress and total:
                        ratio = min(1.0, done / total)
                        self._tasks.put((lambda r: self.update_progress(r), ratio))
            except Exception as exc:  # noqa: BLE001
                self._tasks.put((on_error or self._default_error, exc))
            else:
                self._tasks.put((on_success, None))
            finally:
                self._tasks.put((release, None))

        threading.Thread(target=worker, daemon=True).start()

    def _default_error(self, exc: Exception) -> None:
        if isinstance(exc, JsonError):
            self.status(f"JSON 解析失败：{exc}", "err")
        else:
            self.status(f"{type(exc).__name__}：{exc}", "err")


__all__ = ["Card", "CodeText", "Page"]
