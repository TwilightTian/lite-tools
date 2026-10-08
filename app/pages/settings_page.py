"""设置页：开机自启 / 全局快捷键 / 托盘 / 配置文件。"""

from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from tkinter import ttk

from .. import theme
from ..config import APP_TITLE, APP_VERSION, CONFIG_DIR, CONFIG_PATH
from ..native import autostart
from ..native import hotkey as hk
from ..theme import PALETTE
from ..widgets import Card, FlowFrame, button, check_box
from .base import Page

KEY_CHOICES = [chr(c) for c in range(ord("A"), ord("Z") + 1)] + [f"F{i}" for i in range(1, 13)]
MODIFIER_CHOICES = [("ctrl", "Ctrl"), ("alt", "Alt"), ("shift", "Shift"), ("win", "Win")]


class SettingsPage(Page):
    title = "设置"
    desc = "开机自启 · 全局快捷键 · 托盘与窗口行为"

    def build(self) -> None:
        startup = Card(self.body, title="启动与窗口", stretch=False)
        startup.grid(row=0, column=0, sticky="ew")
        self._build_startup(startup.content)

        shortcut = Card(self.body, title="全局快捷键",
                        hint="在任何程序中按下即可呼出或隐藏主窗口", stretch=False)
        shortcut.grid(row=1, column=0, sticky="ew", pady=(theme.sp(10), 0))
        self._build_hotkey(shortcut.content)

        about = Card(self.body, title="关于", stretch=False)
        about.grid(row=2, column=0, sticky="ew", pady=(theme.sp(10), 0))
        self._build_about(about.content)

    # ------------------------------------------------------------ 组件
    def _check(self, parent: tk.Frame, text: str, variable: tk.BooleanVar,
               command=None) -> tk.Checkbutton:
        return check_box(parent, text, variable, command=command,
                         parent_bg=PALETTE["card"])

    def _hint(self, parent: tk.Frame, textvariable=None, text: str = "") -> tk.Label:
        return tk.Label(
            parent, textvariable=textvariable, text=text, background=PALETTE["card"],
            foreground=PALETTE["dim"], font=theme.ui_small,
            anchor="w", justify="left", wraplength=theme.sp(820),
        )

    # ------------------------------------------------------------ 启动项
    def _build_startup(self, parent: tk.Frame) -> None:
        self.auto_start_var = tk.BooleanVar(value=autostart.is_enabled())
        self._check(parent, "开机自动启动", self.auto_start_var,
                    command=self._on_auto_start).pack(anchor="w")

        self.start_min_var = tk.BooleanVar(
            value=bool(self.config.get("startup.start_minimized", False)))
        self._check(parent, "启动后直接最小化到托盘", self.start_min_var,
                    command=self._save_startup).pack(anchor="w", pady=(theme.sp(4), 0))

        self.close_tray_var = tk.BooleanVar(
            value=bool(self.config.get("startup.close_to_tray", False)))
        self._check(parent, "点击关闭按钮时最小化到托盘（而不是退出）", self.close_tray_var,
                    command=self._save_startup).pack(anchor="w", pady=(theme.sp(4), 0))

        self.topmost_var = tk.BooleanVar(
            value=bool(self.config.get("window.always_on_top", False)))
        self._check(parent, "窗口置顶", self.topmost_var,
                    command=self._on_topmost).pack(anchor="w", pady=(theme.sp(4), 0))

        holder = tk.Frame(parent, background=PALETTE["card"])
        holder.pack(fill="x", pady=(theme.sp(9), 0))
        self.startup_hint = self._hint(holder)
        self.startup_hint.pack(anchor="w")
        self._refresh_startup_hint()

    def _refresh_startup_hint(self) -> None:
        state = "已启用" if autostart.is_enabled() else "未启用"
        tray_ok, tray_reason = _tray_status()
        self.startup_hint.configure(
            text=f"自启方式：{autostart.describe()}\n"
                 f"当前状态：{state}      托盘：{'可用' if tray_ok else tray_reason}"
        )

    def _on_auto_start(self) -> None:
        if self.auto_start_var.get():
            ok, message = autostart.enable()
            if not ok:
                self.auto_start_var.set(False)
        else:
            ok, message = autostart.disable()
        self.config.set("startup.auto_start", autostart.is_enabled())
        self.config.save()
        self.status(message, "ok" if ok else "err")
        self._refresh_startup_hint()

    def _save_startup(self) -> None:
        self.config.set("startup.start_minimized", bool(self.start_min_var.get()))
        self.config.set("startup.close_to_tray", bool(self.close_tray_var.get()))
        self.config.save()
        self.status("设置已保存", "ok")

    def _on_topmost(self) -> None:
        value = bool(self.topmost_var.get())
        self.config.set("window.always_on_top", value)
        self.config.save()
        try:
            self.app.root.attributes("-topmost", value)
        except tk.TclError:
            pass
        self.status("窗口置顶已" + ("开启" if value else "关闭"), "ok")

    # ------------------------------------------------------------ 快捷键
    def _build_hotkey(self, parent: tk.Frame) -> None:
        if not hk.IS_WINDOWS:
            self._hint(parent, text="全局快捷键当前仅支持 Windows。").pack(anchor="w")
            self.hotkey_enabled_var = tk.BooleanVar(value=False)
            self.hotkey_key_var = tk.StringVar(value="")
            self.modifier_vars = {}
            self.hotkey_hint = self._hint(parent)
            return

        flow = FlowFrame(parent, parent_bg=PALETTE["card"])
        flow.pack(fill="x")

        self.hotkey_enabled_var = tk.BooleanVar(value=bool(self.config.get("hotkey.enabled", False)))
        flow.add(self._check(flow, "启用", self.hotkey_enabled_var))

        saved_modifiers = [str(m).lower() for m in (self.config.get("hotkey.modifiers", []) or [])]
        self.modifier_vars: dict[str, tk.BooleanVar] = {}
        for name, label in MODIFIER_CHOICES:
            variable = tk.BooleanVar(value=name in saved_modifiers)
            self.modifier_vars[name] = variable
            flow.add(self._check(flow, label, variable))

        key_box = tk.Frame(flow, background=PALETTE["card"])
        tk.Label(key_box, text="主键", background=PALETTE["card"],
                 foreground=PALETTE["text"], font=theme.ui_font).pack(side="left",
                                                                      padx=(0, theme.sp(6)))
        self.hotkey_key_var = tk.StringVar(
            value=str(self.config.get("hotkey.key", "L") or "L").upper())
        ttk.Combobox(key_box, textvariable=self.hotkey_key_var, values=KEY_CHOICES,
                     width=5).pack(side="left")
        flow.add(key_box)

        self.btn_apply_hotkey = button(flow, "应用快捷键", self.apply_hotkey, kind="primary")
        flow.add(self.btn_apply_hotkey)
        flow.add(button(flow, "测试", self._test_hotkey, kind="ghost"))

        self.hotkey_hint = self._hint(parent)
        self.hotkey_hint.pack(anchor="w", pady=(theme.sp(9), 0))
        self._refresh_hotkey_hint()

    def _refresh_hotkey_hint(self) -> None:
        if not hk.IS_WINDOWS:
            return
        modifiers = [name for name, variable in self.modifier_vars.items() if variable.get()]
        text = hk.describe(modifiers, self.hotkey_key_var.get())
        enabled = bool(self.hotkey_enabled_var.get())
        self.hotkey_hint.configure(
            text=f"当前组合：{text}（{'已启用' if enabled else '未启用'}）       "
                 "组合需要至少一个修饰键，若被其它软件占用会提示注册失败。"
        )

    def apply_hotkey(self) -> None:
        modifiers = [name for name, variable in self.modifier_vars.items() if variable.get()]
        key = self.hotkey_key_var.get().strip().upper()
        self.config.set("hotkey.enabled", bool(self.hotkey_enabled_var.get()))
        self.config.set("hotkey.modifiers", modifiers)
        self.config.set("hotkey.key", key)
        self.config.save()
        ok, message = self.app.apply_hotkey()
        if not ok:
            self.hotkey_enabled_var.set(False)
            self.config.set("hotkey.enabled", False)
            self.config.save()
            self.app.apply_hotkey()
        self.status(message, "ok" if ok else "err")
        self._refresh_hotkey_hint()

    def _test_hotkey(self) -> None:
        self.status("已触发一次窗口切换（等同按下快捷键）", "ok")
        self.app.toggle()

    # ------------------------------------------------------------ 关于
    def _build_about(self, parent: tk.Frame) -> None:
        tk.Label(parent, text=f"{APP_TITLE} v{APP_VERSION}", background=PALETTE["card"],
                 foreground=PALETTE["text"], font=theme.section_font).pack(anchor="w")
        tk.Label(
            parent,
            text="纯 Python + Tkinter 实现的跨平台开发小工具箱，运行时只依赖标准库，"
                 "打包后为单文件可执行程序（约 15 MB）。",
            background=PALETTE["card"], foreground=PALETTE["dim"], font=theme.ui_small,
            anchor="w", justify="left", wraplength=theme.sp(820),
        ).pack(anchor="w", pady=(theme.sp(4), 0))

        info = tk.Frame(parent, background=PALETTE["card"])
        info.pack(fill="x", pady=(theme.sp(10), 0))
        for label, value in (("Python", sys.version.split()[0]),
                             ("平台", sys.platform),
                             ("配置", str(CONFIG_PATH))):
            line = tk.Frame(info, background=PALETTE["card"])
            line.pack(fill="x", pady=theme.sp(1))
            tk.Label(line, text=label, background=PALETTE["card"],
                     foreground=PALETTE["dim"], font=theme.ui_small,
                     width=7, anchor="w").pack(side="left")
            tk.Label(line, text=value, background=PALETTE["card"],
                     foreground=PALETTE["text"], font=theme.ui_small,
                     anchor="w").pack(side="left", fill="x", expand=True)

        actions = FlowFrame(parent, parent_bg=PALETTE["card"])
        actions.pack(fill="x", pady=(theme.sp(10), 0))
        actions.add(button(actions, "打开配置目录", self.open_config_dir))
        actions.add(button(actions, "打开配置文件", self.open_config_file))
        actions.add(button(actions, "重置窗口位置", self.reset_geometry, kind="ghost"))

    def open_config_dir(self) -> None:
        self._open_path(CONFIG_DIR)

    def open_config_file(self) -> None:
        if not CONFIG_PATH.exists():
            self.config.save()
        self._open_path(CONFIG_PATH)

    def _open_path(self, path) -> None:
        try:
            if sys.platform == "win32":
                os.startfile(str(path))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
            self.status(f"已打开：{path}", "ok")
        except Exception as exc:  # noqa: BLE001
            self.status(f"打开失败：{exc}", "err")

    def reset_geometry(self) -> None:
        self.config.set("window.x", None)
        self.config.set("window.y", None)
        self.config.save()
        self.status("已重置窗口位置，重启后生效", "ok")

    # ------------------------------------------------------------ 生命周期
    def on_show(self) -> None:
        self.auto_start_var.set(autostart.is_enabled())
        self.topmost_var.set(bool(self.config.get("window.always_on_top", False)))
        self.start_min_var.set(bool(self.config.get("startup.start_minimized", False)))
        self.close_tray_var.set(bool(self.config.get("startup.close_to_tray", False)))
        if hk.IS_WINDOWS:
            self.hotkey_enabled_var.set(bool(self.config.get("hotkey.enabled", False)))
            saved = [str(m).lower() for m in (self.config.get("hotkey.modifiers", []) or [])]
            for name, variable in self.modifier_vars.items():
                variable.set(name in saved)
            self.hotkey_key_var.set(str(self.config.get("hotkey.key", "L") or "L").upper())
            self._refresh_hotkey_hint()
        self._refresh_startup_hint()


def _tray_status() -> tuple[bool, str]:
    """探测托盘可用性。"""
    if sys.platform != "win32":
        return False, "仅 Windows 支持"
    try:
        import win32gui  # noqa: F401
    except ImportError:
        return False, "缺少 pywin32"
    return True, "可用"
