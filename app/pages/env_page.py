"""启动变量转换页：IDEA / Linux export / .env / docker -e / JSON。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .. import theme
from ..core import env_utils as eu
from ..theme import PALETTE
from ..widgets import Card, FlowFrame, SplitPanes, button
from .base import Page

# 示例内容按源格式生成，切换格式时自动换成对应写法
SAMPLE_PAIRS = [
    ("DB_HOST", "127.0.0.1"),
    ("DB_PORT", "3306"),
    ("JAVA_OPTS", "-Xms512m -Xmx1024m"),
    ("SPRING_PROFILES_ACTIVE", "dev"),
]


def sample_for(fmt: str) -> str:
    try:
        return eu.render(SAMPLE_PAIRS, fmt)
    except eu.EnvParseError:
        return ""


class EnvPage(Page):
    title = "启动变量"
    desc = "IDEA Run Configuration、Linux export、.env、docker -e 之间互转"

    def build(self) -> None:
        self.body.rowconfigure(2, weight=1)
        self._sample = ""

        toolbar_card = Card(self.body, padding=(12, 10), stretch=False)
        toolbar_card.grid(row=0, column=0, sticky="ew")
        self.toolbar = FlowFrame(toolbar_card.content, parent_bg=PALETTE["card"])
        self.toolbar.pack(fill="x")
        self._build_toolbar()

        tk.Label(
            self.body,
            text="IDEA 环境变量用分号分隔，值含分号或空格时用双引号包裹；"
                 "转换时会按目标格式自动决定是否需要引号。",
            background=PALETTE["bg"], foreground=PALETTE["dim"], font=theme.ui_small,
            anchor="w", justify="left", wraplength=theme.sp(900),
        ).grid(row=1, column=0, sticky="ew", pady=(theme.sp(6), 0))

        panes = SplitPanes(self.body)
        panes.grid(row=2, column=0, sticky="nsew", pady=(theme.sp(8), 0))

        left = Card(panes.left, title="输入", hint="按源格式书写", min_height=260)
        panes.add(left, "left")
        self.input_area = self.make_code_area(left.content, height=16,
                                              line_numbers=True, wrap=False)
        self.input_area.pack(fill="both", expand=True)
        self._fill_sample()

        right = Card(panes.right, title="输出", min_height=260)
        panes.add(right, "right")
        self.output_area = self.make_code_area(right.content, height=16, editable=False,
                                               line_numbers=True, wrap=False)
        self.output_area.pack(fill="both", expand=True)

    # ------------------------------------------------------------ 工具栏
    def _build_toolbar(self) -> None:
        source_box = tk.Frame(self.toolbar, background=PALETTE["card"])
        tk.Label(source_box, text="源格式", background=PALETTE["card"],
                 foreground=PALETTE["text"], font=theme.ui_font).pack(side="left",
                                                                     padx=(0, theme.sp(6)))
        self.source_var = tk.StringVar(value=str(self.config.get("env.source", "IDEA")))
        source_combo = ttk.Combobox(source_box, textvariable=self.source_var,
                                    values=eu.FORMATS, state="readonly", width=13)
        source_combo.pack(side="left")
        source_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_source_change())
        self.toolbar.add(source_box)

        self.btn_convert = button(self.toolbar, "转换 →", self.do_convert, kind="primary")
        self.toolbar.add(self.btn_convert)
        self.toolbar.add(button(self.toolbar, "← 反向", self.do_reverse))

        target_box = tk.Frame(self.toolbar, background=PALETTE["card"])
        tk.Label(target_box, text="目标格式", background=PALETTE["card"],
                 foreground=PALETTE["text"], font=theme.ui_font).pack(side="left",
                                                                     padx=(0, theme.sp(6)))
        self.target_var = tk.StringVar(
            value=str(self.config.get("env.target", "Linux export"))
        )
        ttk.Combobox(target_box, textvariable=self.target_var, values=eu.FORMATS,
                     state="readonly", width=13).pack(side="left")
        self.toolbar.add(target_box)

        self.toolbar.add(button(self.toolbar, "复制输出", self.do_copy, kind="ghost"))
        self.toolbar.add(button(self.toolbar, "清空", self.do_clear, kind="ghost"))

    def _fill_sample(self) -> None:
        self._sample = sample_for(self.source_var.get())
        self.input_area.set(self._sample)

    def _on_source_change(self) -> None:
        """源格式变了，若输入区还是示例内容就换成新格式的写法。

        用户已经改过内容时保持不动，避免覆盖。
        """
        if self.input_area.get().strip() == self._sample.strip():
            self._fill_sample()

    # ------------------------------------------------------------ 操作
    def _save_formats(self) -> None:
        self.config.set("env.source", self.source_var.get())
        self.config.set("env.target", self.target_var.get())
        self.config.save()

    def do_convert(self) -> None:
        text = self.input_area.get()
        source = self.source_var.get()
        target = self.target_var.get()
        if not text.strip():
            self.status("请输入要转换的内容", "err")
            return
        self._save_formats()

        def work() -> tuple[str, int]:
            result = eu.convert(text, source, target)
            return result, len(eu.parse(text, source))

        def render(payload) -> None:
            result, count = payload
            self.output_area.set(result)
            self.status(f"已从 {source} 转为 {target} · {count} 个变量", "ok")

        self.run_async(work, render, busy=[self.btn_convert])

    def do_reverse(self) -> None:
        text = self.output_area.get() or self.input_area.get()
        if not text.strip():
            self.status("没有可反向转换的内容", "err")
            return
        source, target = self.source_var.get(), self.target_var.get()
        self.source_var.set(target)
        self.target_var.set(source)
        self.input_area.set(text)
        self._save_formats()

        def work() -> tuple[str, int]:
            result = eu.convert(text, target, source)
            return result, len(eu.parse(text, target))

        def render(payload) -> None:
            result, count = payload
            self.output_area.set(result)
            self.status(f"已从 {target} 转为 {source} · {count} 个变量", "ok")

        self.run_async(work, render, busy=[self.btn_convert])

    def do_copy(self) -> None:
        text = self.output_area.get()
        if not text:
            self.status("输出为空", "err")
            return
        self.copy(text)

    def do_clear(self) -> None:
        self.input_area.clear()
        self.output_area.clear()
        self.status("已清空")
