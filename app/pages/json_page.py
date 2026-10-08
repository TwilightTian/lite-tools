"""JSON 工具页：格式化 / 压缩 / 转义 / 校验 / 结构统计，含格式容错。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .. import theme
from ..core import json_utils as ju
from ..theme import PALETTE
from ..widgets import Card, FlowFrame, SplitPanes, button, check_box
from .base import Page

INDENT_CHOICES = ["2 空格", "4 空格", "Tab", "单行"]
INDENT_VALUES = {"2 空格": 2, "4 空格": 4, "Tab": "\t", "单行": None}


class JsonPage(Page):
    title = "JSON 工具"
    desc = "格式化 · 压缩 · 转义 · 校验 · 结构统计"

    def build(self) -> None:
        self.body.rowconfigure(2, weight=1)
        self._action_buttons: list[tk.Widget] = []

        toolbar_card = Card(self.body, padding=(12, 10), stretch=False)
        toolbar_card.grid(row=0, column=0, sticky="ew")
        self.toolbar = FlowFrame(toolbar_card.content, parent_bg=PALETTE["card"])
        self.toolbar.pack(fill="x")
        self._build_toolbar()

        options_card = Card(self.body, padding=(12, 10), stretch=False)
        options_card.grid(row=1, column=0, sticky="ew", pady=(theme.sp(8), 0))
        self.options = FlowFrame(options_card.content, parent_bg=PALETTE["card"])
        self.options.pack(fill="x")
        self._build_options()

        panes = SplitPanes(self.body)
        panes.grid(row=2, column=0, sticky="nsew", pady=(theme.sp(8), 0))

        left = Card(panes.left, title="输入", min_height=230)
        panes.add(left, "left")
        self.input_area = self.make_code_area(left.content, height=14,
                                              line_numbers=True, wrap=False)
        self.input_area.pack(fill="both", expand=True)

        right = Card(panes.right, title="输出", min_height=230)
        panes.add(right, "right")
        self.output_area = self.make_code_area(right.content, height=14, editable=False,
                                               line_numbers=True, wrap=False)
        self.output_area.pack(fill="both", expand=True)

    # ------------------------------------------------------------ 工具栏
    def _build_toolbar(self) -> None:
        actions = (
            ("格式化", self.do_format, "primary"),
            ("压缩", self.do_minify, "normal"),
            ("校验", self.do_validate, "normal"),
            ("结构统计", self.do_stats, "normal"),
            ("转义", self.do_escape, "normal"),
            ("反转义", self.do_unescape, "normal"),
            ("中文 → \\u", self.do_ascii_escape, "normal"),
            ("\\u → 中文", self.do_ascii_unescape, "normal"),
        )
        for text, command, kind in actions:
            widget = button(self.toolbar, text, command, kind=kind)
            self.toolbar.add(widget)
            if text != "校验":
                self._action_buttons.append(widget)

        for text, command in (("结果回填", self.do_feedback),
                              ("复制输出", self.do_copy),
                              ("清空", self.do_clear)):
            self.toolbar.add(button(self.toolbar, text, command, kind="ghost"))

    def _build_options(self) -> None:
        holder = tk.Frame(self.options, background=PALETTE["card"])
        tk.Label(holder, text="缩进", background=PALETTE["card"],
                 foreground=PALETTE["text"], font=theme.ui_font).pack(side="left",
                                                                     padx=(0, theme.sp(6)))
        self.indent_var = tk.StringVar(value=self._indent_label())
        combo = ttk.Combobox(holder, textvariable=self.indent_var, values=INDENT_CHOICES,
                             state="readonly", width=8)
        combo.pack(side="left")
        combo.bind("<<ComboboxSelected>>", lambda _e: self._save_options())
        self.options.add(holder)

        self.sort_var = tk.BooleanVar(value=bool(self.config.get("json.sort_keys", False)))
        self.options.add(self._check("格式化时按键名排序", self.sort_var))

        self.ascii_var = tk.BooleanVar(value=bool(self.config.get("json.ensure_ascii", False)))
        self.options.add(self._check("非 ASCII 输出为 \\uXXXX", self.ascii_var))

        self.lenient_var = tk.BooleanVar(value=bool(self.config.get("json.lenient", True)))
        self.options.add(self._check("宽松模式（自动修复）", self.lenient_var,
                                     command=self._save_options))

    def _check(self, text: str, variable: tk.BooleanVar, command=None):
        return check_box(self.options, text, variable,
                         command=command or self._save_options,
                         parent_bg=PALETTE["card"])

    def _indent_label(self) -> str:
        value = self.config.get("json.indent", 2)
        for label, candidate in INDENT_VALUES.items():
            if candidate == value:
                return label
        return "2 空格"

    def _save_options(self) -> None:
        self.config.set("json.indent", INDENT_VALUES.get(self.indent_var.get(), 2))
        self.config.set("json.sort_keys", bool(self.sort_var.get()))
        self.config.set("json.ensure_ascii", bool(self.ascii_var.get()))
        self.config.set("json.lenient", bool(self.lenient_var.get()))
        self.config.save()

    # ------------------------------------------------------------ 参数
    def _indent(self):
        return INDENT_VALUES.get(self.indent_var.get(), 2)

    def _lenient(self) -> bool:
        return bool(self.lenient_var.get())

    def _require_input(self) -> str:
        text = self.input_area.get()
        if not text.strip():
            self.status("请先在左侧输入内容", "err")
            self.input_area.focus_text()
            return ""
        return text

    def _produce(self, transform, message: str) -> None:
        text = self._require_input()
        if not text:
            return
        lenient = self._lenient()
        report: list[str] = []

        def work() -> str:
            return transform(text, lenient, report)

        def render(result: str) -> None:
            self.output_area.set(result)
            if report:
                self.status(f"{message} · 已自动修复：{'；'.join(report)}", "ok")
            else:
                self.status(f"{message} · 共 {len(result)} 字符", "ok")

        self.run_async(work, render, busy=self._action_buttons)

    # ------------------------------------------------------------ 操作
    def do_format(self) -> None:
        indent = self._indent()
        sort_keys = bool(self.sort_var.get())
        ensure_ascii = bool(self.ascii_var.get())
        self.run_guarded(lambda: self._produce(
            lambda text, lenient, report: ju.format_text(
                text, indent=indent, sort_keys=sort_keys,
                ensure_ascii=ensure_ascii, lenient=lenient, report=report),
            "已格式化",
        ))

    def do_minify(self) -> None:
        ensure_ascii = bool(self.ascii_var.get())
        self.run_guarded(lambda: self._produce(
            lambda text, lenient, report: ju.minify(
                text, ensure_ascii=ensure_ascii, lenient=lenient, report=report),
            "已压缩",
        ))

    def do_validate(self) -> None:
        text = self._require_input()
        if not text:
            return
        lenient = self._lenient()
        report: list[str] = []

        def work() -> str:
            return ju.validate(text, lenient, report)

        def render(message: str) -> None:
            self.status(message, "ok")

        self.run_async(work, render, busy=self._action_buttons)

    def do_stats(self) -> None:
        lenient = self._lenient()
        self.run_guarded(lambda: self._produce(
            lambda text, flag, _report: ju.stats(text, flag), "已生成结构概览",
        ))

    def do_escape(self) -> None:
        text = self.input_area.get()
        if not text:
            self.status("请输入内容", "err")
            return
        self.output_area.set(ju.escape_string(text))
        self.status("已转义为 JSON 字符串字面量", "ok")

    def do_unescape(self) -> None:
        self.run_guarded(lambda: self._produce(
            lambda text, _lenient, _report: ju.unescape_string(text), "已反转义",
        ))

    def do_ascii_escape(self) -> None:
        text = self._require_input()
        if not text:
            return
        indent = self._indent()
        sort_keys = bool(self.sort_var.get())
        lenient = self._lenient()
        report: list[str] = []

        def work() -> str:
            try:
                obj = ju.loads(text, lenient)
            except ju.JsonError:
                return ju.to_ascii_escape(text)
            return ju.dumps(obj, indent=indent or 2, sort_keys=sort_keys, ensure_ascii=True)

        def render(result: str) -> None:
            self.output_area.set(result)
            self.status("已把非 ASCII 字符转为 \\uXXXX"
                        + (f" · 已自动修复：{'；'.join(report)}" if report else ""), "ok")

        self.run_async(work, render, busy=self._action_buttons)

    def do_ascii_unescape(self) -> None:
        self.run_guarded(lambda: self._produce(
            lambda text, _lenient, _report: ju.from_ascii_escape(text), "已还原 \\uXXXX 转义",
        ))

    def do_copy(self) -> None:
        text = self.output_area.get()
        if not text:
            self.status("输出为空", "err")
            return
        self.copy(text)

    def do_feedback(self) -> None:
        """把输出内容搬回输入区，方便连续加工。"""
        text = self.output_area.get()
        if not text:
            self.status("输出为空", "err")
            return
        self.input_area.set(text)
        self.status("已把结果回填到输入区", "ok")

    def do_clear(self) -> None:
        self.input_area.clear()
        self.output_area.clear()
        self.status("已清空")
