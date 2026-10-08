"""主窗口：侧边导航 + 内容区 + 状态栏，并负责托盘与全局快捷键的装配。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from . import theme
from .config import APP_TITLE, APP_VERSION, get_config
from .native import hotkey as hotkey_mod
from .native import icon
from .native import redraw as redraw_mod
from .native import tray as tray_mod
from .pages.codegen_page import CodegenPage
from .pages.env_page import EnvPage
from .pages.json_page import JsonPage
from .pages.net_page import NetPage
from .pages.settings_page import SettingsPage
from .pages.time_page import TimePage
from .theme import PALETTE, RADIUS_BUTTON

NAV_ITEMS = [
    ("json", "JSON 工具", "格式化 · 压缩 · 转义 · 校验", JsonPage),
    ("time", "时间戳转换", "时间戳与各种日期格式互转", TimePage),
    ("env", "启动变量", "IDEA / Linux / .env 环境变量互转", EnvPage),
    ("codegen", "JSON 生成", "Java 实体类 ↔ JSON 双向转换", CodegenPage),
    ("net", "网络工具", "IP 速查 · ping · DNS · telnet", NetPage),
    ("settings", "设置", "开机自启 · 快捷键 · 托盘", SettingsPage),
]

SIDEBAR_WIDTH = 200
# 窗口可以缩得比较窄，靠工具栏自动换行来适配内容
MIN_WIDTH = 720
MIN_HEIGHT = 500
# 连续变化判定为拖动；停止这么久之后恢复重绘
RESIZE_SETTLE_MS = 160
RESIZE_TRIGGER = 3


class NavItem(tk.Canvas):
    """侧边导航项，选中时用圆角底色高亮。"""

    def __init__(self, master: tk.Misc, text: str, command, width: int) -> None:
        self._width = width
        self._text = text
        self._command = command
        height = theme.sp(38)
        super().__init__(master, width=width, height=height,
                         background=PALETTE["sidebar"], highlightthickness=0, bd=0,
                         cursor="hand2", takefocus=0)
        self.selected = False
        self._hover = False
        self.bind("<Button-1>", lambda _e: self._command())
        self.bind("<Enter>", lambda _e: self._set_hover(True))
        self.bind("<Leave>", lambda _e: self._set_hover(False))
        self.bind("<Configure>", lambda _e: self._redraw())
        self._redraw()

    def _set_hover(self, flag: bool) -> None:
        self._hover = flag
        self._redraw()

    def set_selected(self, flag: bool) -> None:
        if flag == self.selected:
            return
        self.selected = flag
        self._redraw()

    def _redraw(self) -> None:
        self.delete("all")
        width = self.winfo_width()
        height = self.winfo_height()
        if width <= 1 or height <= 1:
            width, height = self._width, theme.sp(38)
        radius = theme.sp(RADIUS_BUTTON)
        if self.selected:
            theme.round_rect(self, 0, 0, width, height, radius,
                             fill=PALETTE["accent_soft"], outline=PALETTE["accent_soft"])
            foreground = PALETTE["accent"]
            font = theme.ui_bold
        elif self._hover:
            theme.round_rect(self, 0, 0, width, height, radius,
                             fill=PALETTE["hover"], outline=PALETTE["hover"])
            foreground = PALETTE["text"]
            font = theme.ui_font
        else:
            foreground = PALETTE["text"]
            font = theme.ui_font
        self.create_text(theme.sp(14), height / 2, text=self._text, anchor="w",
                         fill=foreground, font=font)


class MainWindow:
    def __init__(self, start_minimized: bool = False) -> None:
        self.config = get_config()
        self.root = tk.Tk()
        self.root.title(APP_TITLE)
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        self.root.minsize(min(theme.sp(MIN_WIDTH), int(screen_w * 0.7)),
                          min(theme.sp(MIN_HEIGHT), int(screen_h * 0.6)))
        theme.apply(self.root)
        icon.apply_to_window(self.root)

        self.hotkey = hotkey_mod.GlobalHotkey(self.toggle)
        self.tray: tray_mod.TrayIcon | None = None
        self.tray_ready = False
        self.pages: dict[str, tk.Frame] = {}
        self.nav_items: dict[str, NavItem] = {}
        self.current = ""
        self._status_job: str | None = None
        self._quitting = False
        self._resize_hits = 0
        self._resize_job: str | None = None
        self._frozen = False

        self._build_layout()
        self._restore_geometry()
        self._setup_tray()
        self.apply_hotkey()
        self.show_page(self.config.get("window.last_page", "json"))

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.bind("<Control-q>", lambda _e: self.quit())
        self.root.bind("<Configure>", self._on_root_configure, add="+")

        if start_minimized or self.config.get("startup.start_minimized"):
            self.hide_window()

    # ------------------------------------------------------------ 界面构建
    def _build_layout(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        shell = tk.Frame(self.root, background=PALETTE["bg"])
        shell.grid(row=0, column=0, sticky="nsew")
        shell.columnconfigure(1, weight=1)
        shell.rowconfigure(0, weight=1)

        # ---- 侧边栏
        sidebar = tk.Frame(shell, width=theme.sp(SIDEBAR_WIDTH),
                           background=PALETTE["sidebar"])
        sidebar.grid(row=0, column=0, sticky="ns")
        sidebar.grid_propagate(False)

        brand = tk.Frame(sidebar, background=PALETTE["sidebar"],
                         padx=theme.sp(18), pady=theme.sp(18))
        brand.pack(fill="x")
        tk.Label(brand, text="Lite Tools", background=PALETTE["sidebar"],
                 foreground=PALETTE["text"], font=theme.title_font,
                 anchor="w").pack(anchor="w")
        tk.Label(brand, text="开发小工具箱", background=PALETTE["sidebar"],
                 foreground=PALETTE["dim"], font=theme.ui_small,
                 anchor="w").pack(anchor="w", pady=(theme.sp(2), 0))

        nav_holder = tk.Frame(sidebar, background=PALETTE["sidebar"],
                              padx=theme.sp(10))
        nav_holder.pack(fill="both", expand=True)
        item_width = theme.sp(SIDEBAR_WIDTH) - theme.sp(20)
        for key, text, _desc, _cls in NAV_ITEMS:
            item = NavItem(nav_holder, text, lambda k=key: self.show_page(k), item_width)
            item.pack(fill="x", pady=(0, theme.sp(2)))
            self.nav_items[key] = item

        footer = tk.Frame(sidebar, background=PALETTE["sidebar"],
                          padx=theme.sp(18), pady=theme.sp(14))
        footer.pack(fill="x", side="bottom")
        tk.Label(footer, text=f"v{APP_VERSION}", background=PALETTE["sidebar"],
                 foreground=PALETTE["dim"], font=theme.ui_small,
                 anchor="w").pack(anchor="w")

        tk.Frame(shell, width=1, background=PALETTE["border"]).grid(
            row=0, column=0, sticky="nse")

        # ---- 右侧
        right = tk.Frame(shell, background=PALETTE["bg"])
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        header = tk.Frame(right, background=PALETTE["bg"])
        header.grid(row=0, column=0, sticky="ew",
                    padx=theme.sp(18), pady=(theme.sp(14), theme.sp(2)))
        self.title_label = tk.Label(header, text="", background=PALETTE["bg"],
                                    foreground=PALETTE["text"], font=theme.title_font,
                                    anchor="w")
        self.title_label.pack(anchor="w")
        self.desc_label = tk.Label(header, text="", background=PALETTE["bg"],
                                   foreground=PALETTE["dim"], font=theme.ui_small,
                                   anchor="w")
        self.desc_label.pack(anchor="w", pady=(theme.sp(1), 0))

        self.container = tk.Frame(right, background=PALETTE["bg"])
        self.container.grid(row=1, column=0, sticky="nsew")
        self.container.columnconfigure(0, weight=1)
        self.container.rowconfigure(0, weight=1)

        for key, _text, _desc, page_class in NAV_ITEMS:
            page = page_class(self.container, self)
            page.grid(row=0, column=0, sticky="nsew")
            self.pages[key] = page

        # ---- 状态栏
        statusbar = tk.Frame(right, background=PALETTE["card"])
        statusbar.grid(row=2, column=0, sticky="ew")
        tk.Frame(statusbar, height=1, background=PALETTE["border"]).pack(fill="x")
        inner = tk.Frame(statusbar, background=PALETTE["card"],
                         padx=theme.sp(18), pady=theme.sp(6))
        inner.pack(fill="x")
        self.status_label = tk.Label(inner, text="就绪", background=PALETTE["card"],
                                     foreground=PALETTE["dim"], font=theme.ui_small,
                                     anchor="w")
        self.status_label.pack(side="left")
        self.hotkey_label = tk.Label(inner, text="", background=PALETTE["card"],
                                     foreground=PALETTE["dim"], font=theme.ui_small)
        self.hotkey_label.pack(side="right")
        self.refresh_hotkey_hint()

    # ------------------------------------------------------------ 页面切换
    def show_page(self, key: str) -> None:
        if key not in self.pages:
            key = "json"
        if self.current and self.current != key:
            previous = self.pages.get(self.current)
            if hasattr(previous, "on_hide"):
                previous.on_hide()
        self.current = key
        # 只让当前页面留在布局里：否则窗口缩放时，叠在一起的所有页面都要重排和重绘
        for name, candidate in self.pages.items():
            if name == key:
                candidate.grid()
            else:
                candidate.grid_remove()
        page = self.pages[key]
        page.tkraise()
        for name, item in self.nav_items.items():
            item.set_selected(name == key)
        for name, text, desc, _cls in NAV_ITEMS:
            if name == key:
                self.title_label.configure(text=text)
                self.desc_label.configure(text=desc)
                break
        self.config.set("window.last_page", key)
        if hasattr(page, "on_show"):
            page.on_show()

    # ------------------------------------------------------------ 状态栏
    def set_status(self, text: str, kind: str = "info") -> None:
        color = {"info": PALETTE["dim"], "ok": PALETTE["ok"],
                 "err": PALETTE["err"]}.get(kind, PALETTE["dim"])
        self.status_label.configure(text=text, foreground=color)
        if self._status_job:
            try:
                self.root.after_cancel(self._status_job)
            except tk.TclError:
                pass
        if kind != "info":
            self._status_job = self.root.after(6000, self._reset_status)

    def _reset_status(self) -> None:
        self._status_job = None
        self.status_label.configure(text="就绪", foreground=PALETTE["dim"])

    def refresh_hotkey_hint(self) -> None:
        enabled = bool(self.config.get("hotkey.enabled", False))
        if enabled and hotkey_mod.IS_WINDOWS:
            text = "快捷键：" + hotkey_mod.describe(
                self.config.get("hotkey.modifiers", []), self.config.get("hotkey.key", "")
            )
        else:
            text = ""
        self.hotkey_label.configure(text=text)

    # ------------------------------------------------------------ 窗口控制
    def show_window(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        if self.config.get("window.always_on_top", False):
            self.root.attributes("-topmost", True)

    def hide_window(self) -> None:
        self.root.withdraw()

    def toggle(self) -> None:
        """全局快捷键触发：可见则隐藏，隐藏则显示。"""
        try:
            if self.root.state() == "withdrawn" or not self.root.winfo_viewable():
                self.root.after(0, self.show_window)
            else:
                self.root.after(0, self.hide_window)
        except tk.TclError:
            pass

    # ------------------------------------------------------------ 拖动优化
    def _on_root_configure(self, event: tk.Event) -> None:
        """窗口连续变化时暂停重绘，停下来后一次性刷新。

        Tk 缩放时会遍历所有控件重算几何并重绘，控件一多就跟不上鼠标；
        拖动过程中内容本来也看不清，冻结重绘能换来顺滑得多的手感。
        """
        if event.widget is not self.root:
            return
        self._resize_hits += 1
        if not self._frozen and self._resize_hits >= RESIZE_TRIGGER:
            self._frozen = redraw_mod.set_redraw(self.root, False)
        if self._resize_job is not None:
            try:
                self.root.after_cancel(self._resize_job)
            except tk.TclError:
                pass
        self._resize_job = self.root.after(RESIZE_SETTLE_MS, self._end_resize)

    def _end_resize(self) -> None:
        self._resize_job = None
        self._resize_hits = 0
        if self._frozen:
            redraw_mod.set_redraw(self.root, True)
            self._frozen = False

    def on_close(self) -> None:
        if self.config.get("startup.close_to_tray", False) and self.tray_ready:
            self.hide_window()
            self.set_status("已最小化到托盘，右键托盘图标可退出", "ok")
            return
        self.quit()

    def quit(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        if self._frozen:
            redraw_mod.set_redraw(self.root, True)
            self._frozen = False
        self._save_geometry()
        self.hotkey.unregister()
        if self.tray is not None:
            self.tray.stop()
        # 取消自己的延迟任务，避免窗口销毁后定时器继续触发
        for attr in ("_resize_job", "_status_job"):
            job = getattr(self, attr, None)
            if job is not None:
                try:
                    self.root.after_cancel(job)
                except tk.TclError:
                    pass
                setattr(self, attr, None)
        self.config.save()
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    # ------------------------------------------------------------ 装配
    def _setup_tray(self) -> None:
        ok, _reason = tray_mod.available()
        if not ok:
            return
        icon_path = icon.ensure_icon()
        self.tray = tray_mod.TrayIcon(
            self.root, icon_path, f"{APP_TITLE} - 开发小工具箱",
            on_show=self.show_window, on_quit=self.quit,
        )
        self.tray_ready = self.tray.start()

    def apply_hotkey(self) -> tuple[bool, str]:
        enabled = bool(self.config.get("hotkey.enabled", False))
        modifiers = list(self.config.get("hotkey.modifiers", []) or [])
        key = str(self.config.get("hotkey.key", ""))
        ok, message = self.hotkey.apply(enabled, modifiers, key)
        self.refresh_hotkey_hint()
        return ok, message

    # ------------------------------------------------------------ 几何
    def _restore_geometry(self) -> None:
        width = int(self.config.get("window.width", 0) or 0) or theme.sp(1120)
        height = int(self.config.get("window.height", 0) or 0) or theme.sp(740)
        x = self.config.get("window.x")
        y = self.config.get("window.y")
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        width = max(theme.sp(MIN_WIDTH), min(width, int(screen_w * 0.92)))
        height = max(theme.sp(MIN_HEIGHT), min(height, int(screen_h * 0.88)))
        if x is None or y is None:
            x = max(0, (screen_w - width) // 2)
            y = max(0, (screen_h - height) // 3)
        x = min(max(0, int(x)), max(0, screen_w - theme.sp(200)))
        y = min(max(0, int(y)), max(0, screen_h - theme.sp(150)))
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        if self.config.get("window.always_on_top", False):
            self.root.attributes("-topmost", True)

    def _save_geometry(self) -> None:
        try:
            if self.root.state() == "normal":
                self.config.set("window.width", self.root.winfo_width())
                self.config.set("window.height", self.root.winfo_height())
                self.config.set("window.x", self.root.winfo_x())
                self.config.set("window.y", self.root.winfo_y())
        except tk.TclError:
            pass

    # ------------------------------------------------------------ 运行
    def run(self) -> None:
        self.root.mainloop()


def create(start_minimized: bool = False) -> MainWindow:
    return MainWindow(start_minimized=start_minimized)
