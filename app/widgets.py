"""通用界面组件：圆角卡片、圆角按钮、分段页签、流式容器、进度条、代码框。

设计约定：
- 卡片、按钮、页签自绘，保证圆角与配色统一；
- 输入框、下拉框、复选框交给系统原生渲染，保证清晰度；
- 容器一律使用 `tk.Frame` 并显式设置背景色，自绘组件靠 `surface_color()` 推断底色。
"""

from __future__ import annotations

import re
import tkinter as tk
from tkinter import ttk
from typing import Callable, Iterable, Sequence

from . import theme
from .theme import PALETTE, RADIUS_BUTTON, RADIUS_CARD

_JSON_TOKEN = re.compile(
    r'"(?:\\.|[^"\\])*"(\s*:)?'          # 字符串 / 键
    r"|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?"  # 数字
    r"|\b(?:true|false|null)\b"           # 字面量
)

# 滚动容器检查内容高度的间隔（毫秒）
_WATCH_MS = 400
# 拖动窗口时合并重绘的间隔（毫秒），避免逐帧重画圆角造成卡顿
_THROTTLE_MS = 24


# ================================================================ 卡片
class Card(tk.Frame):
    """圆角卡片。内容放进 `card.content`，右上角可放控件到 `card.header`。"""

    def __init__(self, master: tk.Misc, title: str = "", hint: str = "",
                 padding: int | tuple[int, int] = 14, radius: int = RADIUS_CARD,
                 parent_bg: str | None = None, stretch: bool = True,
                 min_height: int = 0) -> None:
        self._parent_bg = parent_bg or theme.surface_color(master)
        super().__init__(master, background=self._parent_bg, highlightthickness=0, bd=0)
        if isinstance(padding, (tuple, list)):
            self._pad_x, self._pad_y = theme.sp(padding[0]), theme.sp(padding[1])
        else:
            self._pad_x = self._pad_y = theme.sp(padding)
        self._radius = theme.sp(radius)
        self._stretch = stretch

        # 背景层用 place 铺满，不参与尺寸计算；内容层用 pack 决定卡片自身大小
        self._canvas = tk.Canvas(self, background=self._parent_bg,
                                 highlightthickness=0, bd=0, takefocus=0)
        self._canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self._bg_size = (0, 0)
        self._bg_job: str | None = None
        self._canvas.bind("<Configure>", self._on_resize)
        self.bind("<Destroy>", self._on_destroy)

        self.body = tk.Frame(self, background=PALETTE["card"])
        self.body.pack(fill="both", expand=True, padx=self._pad_x, pady=self._pad_y)
        if min_height:
            # 固定内容区高度，让卡片在滚动容器里有稳定的自然高度
            self.body.configure(height=theme.sp(min_height))
            self.body.pack_propagate(False)

        self.header: tk.Frame | None = None
        self.content = self.body
        if title:
            self.header = tk.Frame(self.body, background=PALETTE["card"])
            self.header.pack(fill="x", pady=(0, theme.sp(9)))
            tk.Label(self.header, text=title, background=PALETTE["card"],
                     foreground=PALETTE["text"], font=theme.section_font).pack(side="left")
            if hint:
                tk.Label(self.header, text=hint, background=PALETTE["card"],
                         foreground=PALETTE["dim"], font=theme.ui_small).pack(
                    side="left", padx=(theme.sp(10), 0))
            self.content = tk.Frame(self.body, background=PALETTE["card"])
            self.content.pack(fill="both", expand=True)

    def _on_resize(self, event: tk.Event) -> None:
        # Configure 在仅仅移动位置时也会触发，尺寸没变就不必重画
        size = (event.width, event.height)
        if size == self._bg_size:
            return
        self._bg_size = size
        if self._bg_job is None:
            self._bg_job = self.after(_THROTTLE_MS, self._draw_bg)

    def _draw_bg(self) -> None:
        self._bg_job = None
        width, height = self._bg_size
        try:
            self._canvas.delete("bg")
            if width <= 2 or height <= 2:
                return
            theme.round_rect(self._canvas, 0.5, 0.5, width - 0.5, height - 0.5,
                             self._radius, fill=PALETTE["card"],
                             outline=PALETTE["border"], width=1, tags="bg")
            self._canvas.tag_lower("bg")
        except tk.TclError:
            pass

    def _on_destroy(self, event: tk.Event) -> None:
        if event.widget is not self:
            return
        if self._bg_job is not None:
            try:
                self.after_cancel(self._bg_job)
            except tk.TclError:
                pass
            self._bg_job = None


# ================================================================ 按钮
class RoundButton(tk.Canvas):
    """自绘圆角按钮，支持 primary / normal / ghost / danger 四种外观。"""

    _KINDS = ("normal", "primary", "ghost", "danger")

    def __init__(self, master: tk.Misc, text: str, command: Callable[[], None] | None = None,
                 kind: str = "normal", parent_bg: str | None = None,
                 padding: tuple[int, int] = (14, 7), min_width: int = 0,
                 radius: int = RADIUS_BUTTON) -> None:
        self._bg = parent_bg or theme.surface_color(master)
        self.text = text
        self.kind = kind if kind in self._KINDS else "normal"
        self._command = command
        self._pad_x, self._pad_y = theme.sp(padding[0]), theme.sp(padding[1])
        self._radius = theme.sp(radius)
        self._enabled = True
        self._hover = False
        self._pressed = False

        width = max(min_width, theme.ui_font.measure(text) + self._pad_x * 2)
        height = theme.ui_font.metrics("linespace") + self._pad_y * 2

        super().__init__(master, width=width, height=height, background=self._bg,
                         highlightthickness=0, bd=0, cursor="hand2", takefocus=1)

        self._drawn_size = (0, 0)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<space>", self._on_key)
        self.bind("<Return>", self._on_key)
        self.bind("<Configure>", self._on_configure)
        self._redraw()

    def _on_configure(self, event: tk.Event) -> None:
        """仅在尺寸真正变化时重绘；流式布局重排会带来大量位置变化事件。"""
        size = (event.width, event.height)
        if size == self._drawn_size:
            return
        self._drawn_size = size
        self._redraw()

    # ------------------------------------------------------------ 状态
    def set_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled == self._enabled:
            return
        self._enabled = enabled
        self._pressed = self._hover = False
        try:
            self.configure(cursor="hand2" if enabled else "arrow")
        except tk.TclError:
            pass
        self._redraw()

    def set_text(self, text: str) -> None:
        if text == self.text:
            return
        self.text = text
        need = theme.ui_font.measure(text) + self._pad_x * 2
        if need > int(self["width"]):
            self.configure(width=need)
        self._redraw()

    def is_enabled(self) -> bool:
        return self._enabled

    # ------------------------------------------------------------ 事件
    def _on_enter(self, _event=None) -> None:
        if self._enabled:
            self._hover = True
            self._redraw()

    def _on_leave(self, _event=None) -> None:
        self._hover = self._pressed = False
        self._redraw()

    def _on_press(self, _event=None) -> None:
        if not self._enabled:
            return
        self._pressed = True
        self.focus_set()
        self._redraw()

    def _on_release(self, _event=None) -> None:
        if not self._enabled or not self._pressed:
            return
        self._pressed = False
        self._redraw()
        self.invoke()

    def _on_key(self, _event=None) -> None:
        if self._enabled:
            self.invoke()
        return "break"

    def invoke(self) -> None:
        if self._enabled and self._command is not None:
            self._command()

    # ------------------------------------------------------------ 绘制
    def _colors(self) -> tuple[str, str, str]:
        if not self._enabled:
            return PALETTE["disabled_bg"], PALETTE["border"], PALETTE["disabled_fg"]
        if self.kind == "primary":
            fill = PALETTE["accent"]
            if self._pressed:
                fill = PALETTE["accent_pressed"]
            elif self._hover:
                fill = PALETTE["accent_hover"]
            return fill, fill, "#ffffff"
        if self.kind == "danger":
            fill = PALETTE["err"]
            return fill, fill, "#ffffff"
        if self.kind == "ghost":
            if self._hover or self._pressed:
                return PALETTE["accent_soft"], PALETTE["accent_soft"], PALETTE["accent"]
            return self._bg, self._bg, PALETTE["accent"]
        if self._pressed:
            return PALETTE["accent_soft"], PALETTE["accent"], PALETTE["accent"]
        if self._hover:
            return PALETTE["hover"], PALETTE["border_strong"], PALETTE["text"]
        return PALETTE["card"], PALETTE["border_strong"], PALETTE["text"]

    def _redraw(self) -> None:
        self.delete("all")
        width = self.winfo_width()
        height = self.winfo_height()
        if width <= 1 or height <= 1:
            width, height = int(self["width"]), int(self["height"])
        fill, outline, foreground = self._colors()
        theme.round_rect(self, 0.5, 0.5, width - 0.5, height - 0.5, self._radius,
                         fill=fill, outline=outline, width=1)
        self.create_text(width / 2, height / 2 + 1, text=self.text,
                         fill=foreground, font=theme.ui_font)


def button(master: tk.Misc, text: str, command: Callable[[], None],
           kind: str = "normal", min_width: int = 0,
           parent_bg: str | None = None) -> RoundButton:
    """创建圆角按钮的便捷函数。"""
    return RoundButton(master, text, command, kind=kind, parent_bg=parent_bg,
                       min_width=theme.sp(min_width) if min_width else 0)


# ================================================================ 分段页签
class SegmentedControl(tk.Frame):
    """胶囊分段页签，选中项用主色实心块高亮。"""

    def __init__(self, master: tk.Misc, items: Sequence[tuple[str, str]],
                 command: Callable[[str], None] | None = None,
                 parent_bg: str | None = None) -> None:
        self._bg = parent_bg or theme.surface_color(master)
        super().__init__(master, background=self._bg, highlightthickness=0, bd=0)
        self._command = command
        self._tabs: dict[str, tk.Canvas] = {}
        self._labels: dict[str, str] = {}
        self._hover: str | None = None
        self._current = ""
        self._silent = False

        for key, text in items:
            self._labels[key] = text
            width = theme.ui_font.measure(text) + theme.sp(30)
            height = theme.ui_font.metrics("linespace") + theme.sp(14)
            canvas = tk.Canvas(self, width=width, height=height, background=self._bg,
                               highlightthickness=0, bd=0, cursor="hand2", takefocus=0)
            canvas.pack(side="left", padx=(0, theme.sp(4)))
            canvas.bind("<Button-1>", lambda _e, k=key: self.select(k))
            canvas.bind("<Enter>", lambda _e, k=key: self._set_hover(k, True))
            canvas.bind("<Leave>", lambda _e, k=key: self._set_hover(k, False))
            canvas.bind("<Configure>", lambda _e, k=key: self._draw_tab(k))
            self._tabs[key] = canvas

    def select(self, key: str) -> None:
        if key not in self._tabs:
            return
        self._current = key
        for name in self._tabs:
            self._draw_tab(name)
        if self._command is not None and not self._silent:
            self._command(key)

    def set_silent(self, silent: bool) -> None:
        """为 True 时 select 不触发回调（用于外部同步状态）。"""
        self._silent = silent

    def _set_hover(self, key: str, flag: bool) -> None:
        self._hover = key if flag else None
        self._draw_tab(key)

    def _draw_tab(self, key: str) -> None:
        canvas = self._tabs[key]
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width <= 1 or height <= 1:
            width, height = canvas.winfo_reqwidth(), canvas.winfo_reqheight()
        canvas.delete("all")
        selected = key == self._current
        radius = theme.sp(RADIUS_BUTTON)

        if selected:
            theme.round_rect(canvas, 0.5, 0.5, width - 0.5, height - 0.5, radius,
                             fill=PALETTE["accent"], outline=PALETTE["accent"], width=1)
            foreground = "#ffffff"
        elif self._hover == key:
            theme.round_rect(canvas, 0.5, 0.5, width - 0.5, height - 0.5, radius,
                             fill=PALETTE["hover"], outline=PALETTE["hover"], width=1)
            foreground = PALETTE["text"]
        else:
            foreground = PALETTE["dim"]
        canvas.create_text(width / 2, height / 2 + 1, text=self._labels[key],
                           fill=foreground, font=theme.ui_font)


class Tabs(tk.Frame):
    """分段页签 + 内容区，用来替代 ttk.Notebook。"""

    def __init__(self, master: tk.Misc, items: Sequence[tuple[str, str]],
                 parent_bg: str | None = None) -> None:
        self._bg = parent_bg or theme.surface_color(master)
        super().__init__(master, background=self._bg)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        bar = tk.Frame(self, background=self._bg)
        bar.grid(row=0, column=0, sticky="w", pady=(0, theme.sp(10)))
        self.control = SegmentedControl(bar, items, command=self.select, parent_bg=self._bg)
        self.control.pack(side="left")

        self.stack = tk.Frame(self, background=self._bg)
        self.stack.grid(row=1, column=0, sticky="nsew")
        self.stack.columnconfigure(0, weight=1)
        self.stack.rowconfigure(0, weight=1)

        self._pages: dict[str, tk.Frame] = {}
        for key, _text in items:
            frame = tk.Frame(self.stack, background=self._bg)
            frame.grid(row=0, column=0, sticky="nsew")
            self._pages[key] = frame

        if items:
            self.control.set_silent(True)
            self.select(items[0][0])
            self.control.set_silent(False)

    def page(self, key: str) -> tk.Frame:
        return self._pages[key]

    def select(self, key: str) -> None:
        if key not in self._pages:
            return
        self._pages[key].tkraise()
        self.control.set_silent(True)
        self.control.select(key)
        self.control.set_silent(False)


# ================================================================ 流式容器
class FlowFrame(tk.Frame):
    """按可用宽度自动换行的容器，解决窗口变窄时控件被挤掉的问题。"""

    def __init__(self, master: tk.Misc, hgap: int = 8, vgap: int = 8,
                 parent_bg: str | None = None) -> None:
        self._bg = parent_bg or theme.surface_color(master)
        super().__init__(master, background=self._bg, height=1)
        self._hgap = theme.sp(hgap)
        self._vgap = theme.sp(vgap)
        self._items: list[tk.Widget] = []
        self._height = 0
        self._retries = 0
        self._last_width = -1
        self.bind("<Configure>", lambda e: self._relayout(e.width))

    def add(self, widget: tk.Widget) -> tk.Widget:
        self._items.append(widget)
        # 不强制指定尺寸，让控件用自己的自然尺寸渲染，避免复选框之类的控件被裁切
        widget.place(in_=self, x=0, y=0)
        self._last_width = -1
        self.after_idle(self._relayout)
        return widget

    def extend(self, widgets: Iterable[tk.Widget]) -> None:
        for widget in widgets:
            self.add(widget)

    def _relayout(self, width: int | None = None) -> None:
        if width is None:
            width = self.winfo_width()
        if width <= 1:
            # 尚未完成布局，稍后重试；超过次数就放弃（页面不可见时不必重排）
            self._retries += 1
            if self._retries <= 20:
                self.after(30, self._relayout)
            return
        self._retries = 0
        if width == self._last_width:
            # 可用宽度没变，换行结果也不会变
            return
        self._last_width = width
        x = y = 0
        row_height = 0
        for widget in self._items:
            if not widget.winfo_exists():
                continue
            w = widget.winfo_reqwidth()
            h = widget.winfo_reqheight()
            if x > 0 and x + w > width:
                x = 0
                y += row_height + self._vgap
                row_height = 0
            widget.place(x=x, y=y)
            x += w + self._hgap
            row_height = max(row_height, h)
        total = y + row_height if self._items else 0
        if total != self._height:
            self._height = total
            self.configure(height=max(1, total))


# ================================================================ 滚动容器
class ScrollArea(tk.Frame):
    """垂直滚动容器，内容放进 `content`。

    内容自然高度不足时撑满可视区域（卡片仍可拉伸），超过时出现滚动条。
    """

    def __init__(self, master: tk.Misc, parent_bg: str | None = None) -> None:
        bg = parent_bg or theme.surface_color(master)
        super().__init__(master, background=bg)
        self._bg = bg
        self._syncing = False
        self._last_natural = -1
        self._last_visible = -1
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(self, background=bg, highlightthickness=0, bd=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")

        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self._on_scroll_set)

        self.content = tk.Frame(self.canvas, background=bg)
        self._win = self.canvas.create_window(0, 0, anchor="nw", window=self.content)

        self._fit_job: str | None = None
        self._watch_job: str | None = None
        self.bind("<Destroy>", self._on_destroy)
        self.canvas.configure(yscrollincrement=theme.sp(24))
        self.content.bind("<Configure>", lambda _e: self._schedule_fit())
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        # 内容自身的请求高度变化不会触发 Configure，用低频检查兜底
        self._watch_job = self.after(_WATCH_MS, self._watch)
        # 滚轮事件不会沿父子层级冒泡，必须挂在全局再按鼠标位置分发
        self.bind_all("<MouseWheel>", self._on_wheel, add="+")
        self.bind_all("<Button-4>", self._on_wheel, add="+")
        self.bind_all("<Button-5>", self._on_wheel, add="+")

    # ------------------------------------------------------------ 尺寸
    def _on_scroll_set(self, first, last) -> None:
        if float(first) <= 0.0 and float(last) >= 1.0:
            self.scrollbar.grid_remove()
        else:
            self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.scrollbar.set(first, last)

    def _on_canvas_configure(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self._win, width=event.width)
        self._schedule_fit()

    def _schedule_fit(self) -> None:
        if self._fit_job is None:
            self._fit_job = self.after(_THROTTLE_MS, self._run_fit)

    def _run_fit(self) -> None:
        self._fit_job = None
        try:
            self._fit()
        except tk.TclError:
            pass

    def _watch(self) -> None:
        self._watch_job = None
        try:
            if self.winfo_ismapped():
                self._fit()
        except tk.TclError:
            return
        self._watch_job = self.after(_WATCH_MS, self._watch)

    def _on_destroy(self, event: tk.Event) -> None:
        if event.widget is not self:
            return
        for attr in ("_fit_job", "_watch_job"):
            job = getattr(self, attr, None)
            if job is not None:
                try:
                    self.after_cancel(job)
                except tk.TclError:
                    pass
                setattr(self, attr, None)

    def _fit(self) -> None:
        if self._syncing or not self.winfo_exists() or not self.winfo_ismapped():
            return
        visible = self.canvas.winfo_height()
        if visible <= 1:
            return
        natural = self.content.winfo_reqheight()
        if natural == self._last_natural and visible == self._last_visible:
            return
        self._last_natural, self._last_visible = natural, visible

        target = max(natural, visible)
        if abs(self.content.winfo_height() - target) > 2:
            self._syncing = True
            try:
                self.canvas.itemconfigure(self._win, height=target)
            finally:
                self._syncing = False
        width = self.canvas.winfo_width()
        self.canvas.configure(scrollregion=(0, 0, width, target))

    # ------------------------------------------------------------ 滚轮
    def _on_wheel(self, event: tk.Event):
        try:
            if not self.winfo_ismapped():
                return None
        except tk.TclError:
            return None
        widget = self.winfo_containing(event.x_root, event.y_root)
        if widget is None or not self._owns(widget):
            return None
        if self._inner_scrolls(widget):
            return None
        if self.content.winfo_reqheight() <= self.canvas.winfo_height():
            return None
        self.canvas.yview_scroll(_wheel_delta(event), "units")
        return "break"

    def _owns(self, widget: tk.Misc) -> bool:
        node: tk.Misc | None = widget
        while node is not None:
            if node is self:
                return True
            node = getattr(node, "master", None)
        return False

    @staticmethod
    def _inner_scrolls(widget: tk.Misc) -> bool:
        """鼠标下的控件自己能滚动时让给它，否则在代码框上滚会带着整页跑。"""
        node: tk.Misc | None = widget
        while node is not None:
            if isinstance(node, (tk.Text, ttk.Treeview, tk.Listbox)):
                first, last = node.yview()
                return not (first <= 0.001 and last >= 0.999)
            node = getattr(node, "master", None)
        return False

    def scroll_to_top(self) -> None:
        self.canvas.yview_moveto(0.0)


def _wheel_delta(event: tk.Event) -> int:
    """把各平台的滚轮事件换算成 yview_scroll 的步数。"""
    num = getattr(event, "num", None)
    if num == 4:
        return -1
    if num == 5:
        return 1
    delta = getattr(event, "delta", 0) or 0
    if delta == 0:
        return 1
    if abs(delta) >= 120:
        return -int(round(delta / 120.0))
    return -1 if delta > 0 else 1


# ================================================================ 分栏
class SplitPanes(tk.Frame):
    """左右两栏；可用宽度不足时自动改为上下堆叠，避免内容被裁切。

    用法：把左栏控件放进 `panes.left`，右栏控件放进 `panes.right`。
    """

    def __init__(self, master: tk.Misc, min_column: int = 380, gap: int = 8,
                 parent_bg: str | None = None, stretch: bool = True) -> None:
        self._bg = parent_bg or theme.surface_color(master)
        super().__init__(master, background=self._bg)
        self._breakpoint = theme.sp(min_column) * 2 + theme.sp(gap)
        self._gap = theme.sp(gap)
        self._stretch = stretch
        self._stacked: bool | None = None

        self.left = tk.Frame(self, background=self._bg)
        self.right = tk.Frame(self, background=self._bg)
        for holder in (self.left, self.right):
            holder.columnconfigure(0, weight=1)
            holder.rowconfigure(0, weight=1)

        self._children: list[tk.Widget] = []
        self.bind("<Configure>", self._on_configure)
        self.after_idle(self._relayout)

    def add(self, child: tk.Widget, side: str) -> tk.Widget:
        """放置已经以 `left` 或 `right` 为父容器创建的卡片。"""
        if side not in ("left", "right"):
            raise ValueError("side 只能是 'left' 或 'right'")
        _ = side
        child.grid(row=0, column=0, sticky="nsew")
        return child

    def _on_configure(self, event: tk.Event) -> None:
        stacked = event.width < self._breakpoint
        if stacked == self._stacked:
            return
        self._stacked = stacked
        self._apply_layout()

    def _relayout(self) -> None:
        if self._stacked is None:
            self._stacked = self.winfo_width() < self._breakpoint
        self._apply_layout()

    def _apply_layout(self) -> None:
        stacked = bool(self._stacked)
        self.left.grid_forget()
        self.right.grid_forget()
        # 两列两行彻底重置：uniform 也必须清掉。
        # 否则从上一次并排切到堆叠时，残留的等宽约束会把内容挤窄
        # （卡片请求宽度越大挤得越狠，网络页那两张信息卡就吃过这个亏）。
        for index in (0, 1):
            self.columnconfigure(index, weight=0, uniform="")
            self.rowconfigure(index, weight=0, uniform="")

        half = self._gap // 2
        sticky = "nsew" if self._stretch else "new"
        weight = 1 if self._stretch else 0

        if stacked:
            self.columnconfigure(0, weight=1)
            self.rowconfigure(0, weight=weight)
            self.rowconfigure(1, weight=weight)
            self.left.grid(row=0, column=0, sticky=sticky, pady=(0, self._gap))
            self.right.grid(row=1, column=0, sticky=sticky)
        else:
            self.columnconfigure(0, weight=1, uniform="split")
            self.columnconfigure(1, weight=1, uniform="split")
            self.rowconfigure(0, weight=weight)
            self.left.grid(row=0, column=0, sticky=sticky, padx=(0, half))
            self.right.grid(row=0, column=1, sticky=sticky, padx=(half, 0))


# ================================================================ 进度条
class ProgressLine(tk.Canvas):
    """细长圆角进度条，支持确定进度与循环流动两种模式。"""

    def __init__(self, master: tk.Misc, parent_bg: str | None = None,
                 height: int = 4) -> None:
        self._bg = parent_bg or theme.surface_color(master)
        self._bar_height = theme.sp(height)
        super().__init__(master, height=self._bar_height, background=self._bg,
                         highlightthickness=0, bd=0, takefocus=0)
        self._value = 0.0
        self._mode = "idle"
        self._offset = -0.35
        self._job: str | None = None
        self.bind("<Configure>", lambda _e: self._redraw())

    def set(self, ratio: float) -> None:
        self._mode = "determinate"
        self._value = max(0.0, min(1.0, float(ratio)))
        self._cancel()
        self._redraw()

    def start(self) -> None:
        if self._mode == "indeterminate":
            return
        self._mode = "indeterminate"
        self._offset = -0.35
        self._animate()

    def stop(self) -> None:
        self._mode = "idle"
        self._value = 0.0
        self._cancel()
        self._redraw()

    def _cancel(self) -> None:
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None

    def _animate(self) -> None:
        if self._mode != "indeterminate":
            self._job = None
            return
        self._offset += 0.035
        if self._offset > 1.35:
            self._offset = -0.35
        self._redraw()
        self._job = self.after(30, self._animate)

    def _redraw(self) -> None:
        self.delete("all")
        width = self.winfo_width()
        height = self.winfo_height()
        if width <= 2 or height <= 2:
            return
        radius = height / 2
        theme.round_rect(self, 0, 0, width, height, radius,
                         fill=PALETTE["track"], outline=PALETTE["track"])
        if self._mode == "determinate" and self._value > 0:
            self._draw_bar(0, width * self._value, height)
        elif self._mode == "indeterminate":
            start = self._offset * width
            self._draw_bar(max(0.0, start), min(float(width), start + width * 0.32), height)

    def _draw_bar(self, x1: float, x2: float, height: float) -> None:
        if x2 - x1 <= 1:
            return
        theme.round_rect(self, x1, 0, x2, height, height / 2,
                         fill=PALETTE["accent"], outline=PALETTE["accent"])


# ================================================================ 代码框
class CodeText(tk.Frame):
    """带滚动条、可选行号与 JSON 高亮的文本框。"""

    def __init__(self, master: tk.Misc, height: int = 12, width: int = 40,
                 editable: bool = True, highlight: bool = True,
                 line_numbers: bool = False, wrap: bool = True,
                 font=None, placeholder: str = "") -> None:
        bg = theme.surface_color(master)
        super().__init__(master, background=bg)
        self.highlight_enabled = highlight
        self._after_id: str | None = None
        self._placeholder = placeholder
        self._showing_placeholder = False
        self.editable = editable

        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        self.gutter: tk.Text | None = None
        if line_numbers:
            self.gutter = tk.Text(
                self, width=4, padx=theme.sp(8), pady=theme.sp(10), takefocus=0,
                bd=0, relief="flat", background=PALETTE["code_bg"],
                foreground=PALETTE["dim"], font=theme.mono_small,
                cursor="arrow", highlightthickness=0, wrap="none",
            )
            self.gutter.grid(row=0, column=0, sticky="ns")
            self.gutter.configure(state="disabled")

        self.text = tk.Text(
            self, height=height, width=width, wrap="word" if wrap else "none",
            font=font or theme.code_font, bd=0, relief="flat",
            background=PALETTE["code_bg"], foreground=PALETTE["text"],
            insertbackground=PALETTE["text"], selectbackground=PALETTE["selection"],
            selectforeground=PALETTE["text"], padx=theme.sp(11), pady=theme.sp(10),
            highlightthickness=1, highlightbackground=PALETTE["code_bg"],
            highlightcolor=PALETTE["accent"], undo=True, maxundo=-1,
            spacing1=1, spacing3=1,
        )
        self.text.grid(row=0, column=1, sticky="nsew")

        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self._on_scroll)
        scrollbar.grid(row=0, column=2, sticky="ns")
        self.text.configure(yscrollcommand=scrollbar.set)

        if not wrap:
            self._hbar = ttk.Scrollbar(self, orient="horizontal", command=self.text.xview)
            self._hbar.grid(row=1, column=1, sticky="ew")
            self.text.configure(xscrollcommand=self._hbar.set)

        if not editable:
            self.text.configure(state="disabled", cursor="arrow")

            if highlight:
                self.text.bind("<<Modified>>", self._on_modified)
        else:
            if highlight:
                self.text.bind("<<Modified>>", self._on_modified)
                self.text.bind("<KeyRelease>", self._schedule_highlight)
        self.text.edit_modified(False)

        if placeholder:
            self._install_placeholder()

    # ------------------------------------------------------------ 基础操作
    def _on_scroll(self, *args) -> None:
        self.text.yview(*args)
        self._sync_gutter()

    def get(self) -> str:
        if self._showing_placeholder:
            return ""
        return self.text.get("1.0", "end-1c")

    def set(self, content: str, highlight: bool | None = None) -> None:
        self._showing_placeholder = False
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        if content:
            self.text.insert("1.0", content)
        self.text.edit_reset()
        self.text.edit_modified(False)
        if not self.editable:
            self.text.configure(state="disabled")
        if highlight is not False and self.highlight_enabled:
            self._apply_highlight()
        self._sync_gutter()
        self.text.see("1.0")

    def append(self, content: str) -> None:
        self.text.configure(state="normal")
        self.text.insert("end", content + "\n")
        if not self.editable:
            self.text.configure(state="disabled")
        self.text.see("end")

    def clear(self) -> None:
        self.set("")

    def focus_text(self) -> None:
        self.text.focus_set()

    # ------------------------------------------------------------ 内部实现
    def _install_placeholder(self) -> None:
        self.text.insert("1.0", self._placeholder)
        self.text.configure(foreground=PALETTE["dim"])
        self._showing_placeholder = True

        def on_focus_in(_event=None) -> None:
            if self._showing_placeholder:
                self._showing_placeholder = False
                self.text.delete("1.0", "end")
                self.text.configure(foreground=PALETTE["text"])

        def on_focus_out(_event=None) -> None:
            if not self.text.get("1.0", "end-1c").strip():
                self._showing_placeholder = True
                self.text.delete("1.0", "end")
                self.text.insert("1.0", self._placeholder)
                self.text.configure(foreground=PALETTE["dim"])

        self.text.bind("<FocusIn>", on_focus_in, add="+")
        self.text.bind("<FocusOut>", on_focus_out, add="+")

    def _on_modified(self, _event=None) -> None:
        self._sync_gutter()
        self.text.edit_modified(False)

    def _sync_gutter(self) -> None:
        if self.gutter is None:
            return
        content = self.text.get("1.0", "end-1c")
        lines = content.count("\n") + 1
        first = int(self.text.index("@0,0").split(".")[0])
        last = int(self.text.index(f"@0,{self.text.winfo_height()}").split(".")[0])
        self.gutter.configure(state="normal", width=max(3, len(str(lines))))
        self.gutter.delete("1.0", "end")
        self.gutter.insert("1.0", "\n".join(str(n) for n in range(first, min(last, lines) + 1)))
        self.gutter.configure(state="disabled")
        self.gutter.yview_moveto(self.text.yview()[0])

    def _schedule_highlight(self, _event=None) -> None:
        if self._after_id:
            self.after_cancel(self._after_id)
        self._after_id = self.after(180, self._apply_highlight)

    def _apply_highlight(self) -> None:
        self._after_id = None
        content = self.text.get("1.0", "end-1c")
        for tag in ("j_key", "j_str", "j_num", "j_kw"):
            self.text.tag_remove(tag, "1.0", "end")
        if len(content) > 400_000:
            return
        self.text.tag_configure("j_key", foreground="#0b5cad")
        self.text.tag_configure("j_str", foreground="#1a7f37")
        self.text.tag_configure("j_num", foreground="#b45309")
        self.text.tag_configure("j_kw", foreground="#8250df")
        for match in _JSON_TOKEN.finditer(content):
            start, end = match.start(), match.end()
            if match.group(1):
                self.text.tag_add("j_key", f"1.0+{start}c",
                                  f"1.0+{end - len(match.group(1))}c")
            elif content[start] == '"':
                self.text.tag_add("j_str", f"1.0+{start}c", f"1.0+{end}c")
            elif content[start] in "-0123456789":
                self.text.tag_add("j_num", f"1.0+{start}c", f"1.0+{end}c")
            else:
                self.text.tag_add("j_kw", f"1.0+{start}c", f"1.0+{end}c")


# ================================================================ 辅助
def check_box(master: tk.Misc, text: str, variable: tk.BooleanVar,
              command: Callable[[], None] | None = None,
              parent_bg: str | None = None) -> tk.Checkbutton:
    """统一风格的复选框。

    自带左右内边距，放进 FlowFrame 时不会和相邻控件挤在一起。
    """
    background = parent_bg or theme.surface_color(master)
    return tk.Checkbutton(
        master, text=text, variable=variable,
        background=background, foreground=PALETTE["text"],
        activebackground=background, activeforeground=PALETTE["text"],
        selectcolor=PALETTE["card"], font=theme.ui_font,
        bd=0, highlightthickness=0, padx=theme.sp(3), cursor="hand2",
        command=command,
    )


def separator(master: tk.Misc, pady: int = 8) -> tk.Frame:
    line = tk.Frame(master, height=1, background=PALETTE["border"])
    line.pack(fill="x", pady=theme.sp(pady))
    return line


def copy_to_clipboard(root: tk.Misc, text: str) -> None:
    root.clipboard_clear()
    root.clipboard_append(text)


def add_context_menu(widget: tk.Text, copy_command: Callable[[], None] | None = None,
                     paste: bool = True) -> None:
    """给 Text 组件挂上右键菜单。"""
    menu = tk.Menu(widget, tearoff=0, font=theme.ui_small)
    menu.add_command(label="复制", command=copy_command or (lambda: _copy_selection(widget)))
    if paste:
        menu.add_command(label="粘贴", command=lambda: _paste(widget))
    menu.add_separator()
    menu.add_command(label="全选", command=lambda: _select_all(widget))
    menu.add_command(label="清空", command=lambda: widget.delete("1.0", "end"))

    def popup(event: tk.Event) -> None:
        widget.focus_set()
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    widget.bind("<Button-3>", popup, add="+")


def _copy_selection(widget: tk.Text) -> None:
    try:
        text = widget.get("sel.first", "sel.last")
    except tk.TclError:
        text = widget.get("1.0", "end-1c")
    widget.clipboard_clear()
    widget.clipboard_append(text)


def _paste(widget: tk.Text) -> None:
    try:
        data = widget.clipboard_get()
    except tk.TclError:
        return
    try:
        widget.delete("sel.first", "sel.last")
    except tk.TclError:
        pass
    widget.insert("insert", data)


def _select_all(widget: tk.Text) -> None:
    widget.tag_add("sel", "1.0", "end-1c")


__all__ = [
    "Card",
    "CodeText",
    "FlowFrame",
    "ProgressLine",
    "RoundButton",
    "ScrollArea",
    "SegmentedControl",
    "SplitPanes",
    "Tabs",
    "add_context_menu",
    "button",
    "check_box",
    "copy_to_clipboard",
    "separator",
]
