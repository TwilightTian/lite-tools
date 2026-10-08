"""界面主题：DPI 缩放、配色、字体与圆角绘制。

设计原则：
- 交互控件（输入框、下拉框、复选框、表格、滚动条）交给系统原生渲染，保证清晰度；
- 卡片、按钮、页签等自绘，保证圆润统一的观感；
- 所有像素尺寸经 `sp()` 缩放，配合 DPI 感知保证高分屏下比例正确。
"""

from __future__ import annotations

import ctypes
import math
import sys
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

# ---------------------------------------------------------------- 配色
PALETTE = {
    "bg": "#f3f4f6",
    "card": "#ffffff",
    "sidebar": "#ffffff",
    "border": "#e5e7eb",
    "border_strong": "#d5d9df",
    "text": "#1f2328",
    "dim": "#6b7280",
    "accent": "#2f6fed",
    "accent_hover": "#1f5bd7",
    "accent_pressed": "#1a4cbb",
    "accent_soft": "#eaf1fe",
    "hover": "#f2f4f7",
    "ok": "#15803d",
    "warn": "#b45309",
    "err": "#dc2626",
    "code_bg": "#f7f8fa",
    "selection": "#cfe2ff",
    "disabled_bg": "#eef0f3",
    "disabled_fg": "#a8aeb8",
    "track": "#e8ebf0",
}

RADIUS_CARD = 12
RADIUS_BUTTON = 8
RADIUS_CHIP = 999

_UI_FAMILIES = ["Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC",
                "Segoe UI", "Noto Sans CJK SC", "Helvetica"]
_CODE_FAMILIES = ["Cascadia Mono", "Consolas", "JetBrains Mono", "Menlo",
                  "DejaVu Sans Mono", "Courier New"]

# 由 apply() 创建，调用方请始终通过 theme.xxx 访问
ui_font: tkfont.Font = None  # type: ignore[assignment]
ui_bold: tkfont.Font = None  # type: ignore[assignment]
ui_small: tkfont.Font = None  # type: ignore[assignment]
title_font: tkfont.Font = None  # type: ignore[assignment]
section_font: tkfont.Font = None  # type: ignore[assignment]
code_font: tkfont.Font = None  # type: ignore[assignment]
mono_small: tkfont.Font = None  # type: ignore[assignment]

_scale = 1.0


# ---------------------------------------------------------------- 缩放
def set_scale(factor: float) -> None:
    global _scale
    _scale = max(0.75, min(3.0, float(factor)))


def ui_scale() -> float:
    return _scale


def sp(value: float) -> int:
    """把设计尺寸换算成当前 DPI 下的像素值。"""
    return max(1, int(round(value * _scale)))


def enable_dpi_awareness() -> float:
    """开启进程 DPI 感知并返回缩放因子。必须在创建 Tk 根窗口之前调用。

    不做这一步时，Windows 会对整个窗口做位图拉伸，文字会明显发虚。
    """
    if sys.platform != "win32":
        return 1.0
    aware = False
    try:
        # 1 = PROCESS_SYSTEM_DPI_AWARE，比 per-monitor 更稳妥（Tk 不处理显示器间 DPI 切换）
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        aware = True
    except Exception:  # noqa: BLE001
        try:
            ctypes.windll.user32.SetProcessDPIAware()
            aware = True
        except Exception:  # noqa: BLE001
            aware = False
    if not aware:
        return 1.0

    dpi = 96
    try:
        dpi = int(ctypes.windll.user32.GetDpiForSystem())
    except Exception:  # noqa: BLE001
        try:
            hdc = ctypes.windll.user32.GetDC(0)
            dpi = int(ctypes.windll.gdi32.GetDeviceCaps(hdc, 88))  # LOGPIXELSX
            ctypes.windll.user32.ReleaseDC(0, hdc)
        except Exception:  # noqa: BLE001
            dpi = 96
    factor = dpi / 96.0
    set_scale(factor)
    return factor


# ---------------------------------------------------------------- 绘制
def round_rect(canvas: tk.Canvas, x1: float, y1: float, x2: float, y2: float,
               radius: float, steps: int = 8, **kwargs) -> int:
    """在 Canvas 上画圆角矩形。

    用四段精确圆弧拼成多边形，而不是交给 Tk 的 `smooth` 做贝塞尔拟合：
    拟合曲线在圆角与直边接壤处会轻微偏移，1px 描边会因此断成一截一截的。
    顺带也更快——这里只有 30 多个顶点，拟合会插值出上百个。
    """
    radius = max(0.0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
    points: list[float] = []
    corners = (
        (x2 - radius, y1 + radius, -90.0),   # 右上
        (x2 - radius, y2 - radius, 0.0),     # 右下
        (x1 + radius, y2 - radius, 90.0),    # 左下
        (x1 + radius, y1 + radius, 180.0),   # 左上
    )
    for cx, cy, start in corners:
        for step in range(steps + 1):
            angle = math.radians(start + 90.0 * step / steps)
            points.append(cx + radius * math.cos(angle))
            points.append(cy + radius * math.sin(angle))
    return canvas.create_polygon(points, smooth=False, **kwargs)


def surface_color(widget: tk.Misc) -> str:
    """推断控件所在容器的背景色，自绘组件用它来“透明”融合。"""
    try:
        color = widget.cget("background")
        if color:
            return str(color)
    except (tk.TclError, AttributeError):
        pass
    try:
        style = str(widget.cget("style"))
        if style:
            return str(ttk.Style(widget).lookup(style, "background") or PALETTE["bg"])
    except (tk.TclError, AttributeError):
        pass
    return PALETTE["bg"]


def _pick(candidates: list[str], fallback: str) -> str:
    try:
        available = {name.lower() for name in tkfont.families()}
    except tk.TclError:
        return fallback
    for name in candidates:
        if name.lower() in available:
            return name
    return fallback


# ---------------------------------------------------------------- 应用
def apply(root: tk.Misc) -> ttk.Style:
    """应用全局主题，返回 ttk.Style 实例。"""
    global ui_font, ui_bold, ui_small, title_font, section_font, code_font, mono_small

    ui_family = _pick(_UI_FAMILIES, "Segoe UI")
    code_family = _pick(_CODE_FAMILIES, "Courier New")
    base_size = 10 if sys.platform == "win32" else 11

    ui_font = tkfont.Font(family=ui_family, size=base_size)
    ui_bold = tkfont.Font(family=ui_family, size=base_size, weight="bold")
    ui_small = tkfont.Font(family=ui_family, size=base_size - 1)
    title_font = tkfont.Font(family=ui_family, size=base_size + 6, weight="bold")
    section_font = tkfont.Font(family=ui_family, size=base_size + 2, weight="bold")
    code_font = tkfont.Font(family=code_family, size=base_size)
    mono_small = tkfont.Font(family=code_family, size=base_size - 1)

    if sys.platform == "win32":
        try:
            root.tk.call("tk", "scaling", _scale * 96 / 72.0)
        except tk.TclError:
            pass

    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont"):
        try:
            tkfont.nametofont(name).configure(family=ui_family, size=base_size)
        except tk.TclError:
            pass
    try:
        tkfont.nametofont("TkHeadingFont").configure(
            family=ui_family, size=base_size, weight="bold"
        )
    except tk.TclError:
        pass

    style = ttk.Style(root)
    # 优先使用系统原生主题：控件由系统绘制，边缘与文字清晰得多
    for candidate in ("vista", "winnative", "aqua", "clam"):
        if candidate in style.theme_names():
            try:
                style.theme_use(candidate)
                break
            except tk.TclError:
                continue

    root.configure(background=PALETTE["bg"])

    # 原生主题下只配置确实生效的部分，其余交给系统绘制
    style.configure("TFrame", background=PALETTE["bg"])
    style.configure("TLabel", background=PALETTE["bg"], foreground=PALETTE["text"])
    style.configure("TSeparator", background=PALETTE["border"])

    try:
        style.configure("Treeview", rowheight=sp(26), background=PALETTE["card"],
                        fieldbackground=PALETTE["card"], foreground=PALETTE["text"],
                        bordercolor=PALETTE["border"], lightcolor=PALETTE["card"],
                        darkcolor=PALETTE["card"])
        style.map("Treeview", background=[("selected", PALETTE["accent_soft"])],
                  foreground=[("selected", PALETTE["text"])])
    except tk.TclError:
        pass

    # 表头在原生主题下由系统绘制，只有 clam 这类主题支持自定义配色
    try:
        style.configure("Treeview.Heading", font=ui_bold, padding=(sp(8), sp(6)),
                        background=PALETTE["hover"], foreground=PALETTE["dim"],
                        relief="flat", borderwidth=0)
        style.map("Treeview.Heading",
                  background=[("active", PALETTE["accent_soft"])],
                  foreground=[("active", PALETTE["accent"])])
    except tk.TclError:
        pass

    try:
        style.configure("TNotebook", background=PALETTE["bg"], borderwidth=0)
        style.configure("TNotebook.Tab", padding=(sp(16), sp(6)))
    except tk.TclError:
        pass

    return style


def bg_of(widget: tk.Misc) -> str:
    return surface_color(widget)
