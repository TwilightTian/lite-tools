"""时间戳转换页。"""

from __future__ import annotations

import tkinter as tk
from datetime import datetime
from tkinter import ttk

from .. import theme
from ..core import time_utils as tu
from ..theme import PALETTE
from ..widgets import Card, FlowFrame, button, check_box
from .base import Page

ZONE_CHOICES = ["本地时区", "UTC", "UTC+8 北京", "UTC+9 东京", "UTC-5 纽约", "UTC-8 洛杉矶"]
ZONE_OFFSETS = {
    "本地时区": "local",
    "UTC": "UTC",
    "UTC+8 北京": 8,
    "UTC+9 东京": 9,
    "UTC-5 纽约": -5,
    "UTC-8 洛杉矶": -8,
}

PRESETS = [
    ("yyyy-MM-dd", "%Y-%m-%d"),
    ("yyyy/MM/dd HH:mm", "%Y/%m/%d %H:%M"),
    ("yyyyMMdd", "%Y%m%d"),
    ("HH:mm:ss", "%H:%M:%S"),
]


class TimePage(Page):
    title = "时间戳转换"
    desc = "时间戳与常见日期格式互转，含时区换算"

    def build(self) -> None:
        self.body.rowconfigure(3, weight=1)
        self._tick_job: str | None = None

        clock = Card(self.body, padding=(16, 12), stretch=False)
        clock.grid(row=0, column=0, sticky="ew")
        self._build_clock(clock.content)

        form = Card(self.body, padding=(12, 10), stretch=False)
        form.grid(row=1, column=0, sticky="ew", pady=(theme.sp(8), 0))
        self.form = FlowFrame(form.content, parent_bg=PALETTE["card"])
        self.form.pack(fill="x")
        self._build_form()

        hint = tk.Frame(self.body, background=PALETTE["bg"])
        hint.grid(row=2, column=0, sticky="ew", pady=(theme.sp(6), 0))
        tk.Label(
            hint,
            text="支持：10/13/16 位时间戳、now、2024-03-05 12:30:00、2024-03-05、2024/03/05、"
                 "20240305、20240305123000、12:30、ISO8601、RFC2822、Nginx 日志时间。"
                 "上排按钮可直接按对应格式复制。",
            background=PALETTE["bg"], foreground=PALETTE["dim"],
            font=theme.ui_small, anchor="w", justify="left", wraplength=theme.sp(900),
        ).pack(anchor="w")

        result = Card(self.body, title="转换结果", hint="双击任意行复制该项的值",
                      min_height=300)
        result.grid(row=3, column=0, sticky="nsew", pady=(theme.sp(8), 0))
        self._build_result(result.content)

    # ------------------------------------------------------------ 当前时间
    def _build_clock(self, parent: tk.Frame) -> None:
        row = tk.Frame(parent, background=PALETTE["card"])
        row.pack(fill="x")

        left = tk.Frame(row, background=PALETTE["card"])
        left.pack(side="left", fill="x", expand=True)
        self.clock_label = tk.Label(left, text="", background=PALETTE["card"],
                                    foreground=PALETTE["text"], font=theme.title_font,
                                    anchor="w")
        self.clock_label.pack(anchor="w")
        self.clock_sub = tk.Label(left, text="", background=PALETTE["card"],
                                  foreground=PALETTE["dim"], font=theme.ui_small, anchor="w")
        self.clock_sub.pack(anchor="w", pady=(theme.sp(2), 0))

        right = FlowFrame(row, parent_bg=PALETTE["card"])
        right.pack(side="right", anchor="ne")
        self.auto_var = tk.BooleanVar(value=bool(self.config.get("time.auto_refresh", True)))
        right.add(check_box(right, "实时刷新", self.auto_var,
                            command=self._on_auto_toggle, parent_bg=PALETTE["card"]))
        right.add(button(right, "复制秒", self.copy_now_seconds, kind="ghost",
                         parent_bg=PALETTE["card"]))
        right.add(button(right, "复制毫秒", self.copy_now_millis, kind="ghost",
                         parent_bg=PALETTE["card"]))

    def copy_now_seconds(self) -> None:
        self.copy(str(int(datetime.now().timestamp())), "已复制当前 Unix 秒")

    def copy_now_millis(self) -> None:
        self.copy(str(tu.now_millis()), "已复制当前 Unix 毫秒")

    def _on_auto_toggle(self) -> None:
        self.config.set("time.auto_refresh", bool(self.auto_var.get()))
        if self.auto_var.get():
            self._start_tick()
        else:
            self._stop_tick()

    def _start_tick(self) -> None:
        if self._tick_job is None:
            self._tick()

    def _stop_tick(self) -> None:
        if self._tick_job is not None:
            try:
                self.after_cancel(self._tick_job)
            except tk.TclError:
                pass
            self._tick_job = None

    def _tick(self) -> None:
        now = datetime.now()
        self.clock_label.configure(text=now.strftime("%Y-%m-%d %H:%M:%S"))
        self.clock_sub.configure(
            text=f"Unix 秒 {int(now.timestamp())}    Unix 毫秒 {int(now.timestamp() * 1000)}"
                 f"    {tu.WEEKDAYS_CN[now.weekday()]}"
        )
        if self.auto_var.get():
            self._tick_job = self.after(200, self._tick)
        else:
            self._tick_job = None

    # ------------------------------------------------------------ 输入
    def _build_form(self) -> None:
        field = tk.Frame(self.form, background=PALETTE["card"])
        tk.Label(field, text="输入", background=PALETTE["card"],
                 foreground=PALETTE["text"], font=theme.ui_font).pack(side="left",
                                                                     padx=(0, theme.sp(6)))
        self.input_var = tk.StringVar()
        self.entry = ttk.Entry(field, textvariable=self.input_var, font=theme.code_font,
                               width=26)
        self.entry.pack(side="left")
        self.entry.bind("<Return>", lambda _e: self.do_convert())
        self.form.add(field)

        zone_box = tk.Frame(self.form, background=PALETTE["card"])
        tk.Label(zone_box, text="输入时区", background=PALETTE["card"],
                 foreground=PALETTE["text"], font=theme.ui_font).pack(side="left",
                                                                     padx=(0, theme.sp(6)))
        self.zone_var = tk.StringVar(value=self.config.get("time.zone", ZONE_CHOICES[0]))
        zone = ttk.Combobox(zone_box, textvariable=self.zone_var, values=ZONE_CHOICES,
                            state="readonly", width=12)
        zone.pack(side="left")
        zone.bind("<<ComboboxSelected>>", lambda _e: self._on_zone_change())
        self.form.add(zone_box)

        self.btn_convert = button(self.form, "转换", self.do_convert, kind="primary")
        self.form.add(self.btn_convert)
        self.form.add(button(self.form, "现在", self.fill_now))
        self.btn_s_to_ms = button(self.form, "秒→毫秒", self.do_s_to_ms)
        self.form.add(self.btn_s_to_ms)
        self.btn_ms_to_s = button(self.form, "毫秒→秒", self.do_ms_to_s)
        self.form.add(self.btn_ms_to_s)
        self.input_var.trace_add("write", lambda *_: self._sync_ts_buttons())
        self._sync_ts_buttons()

        for label, pattern in PRESETS:
            self.form.add(button(self.form, label, lambda p=pattern: self._copy_with_pattern(p),
                                 kind="ghost"))

    def _on_zone_change(self) -> None:
        self.config.set("time.zone", self.zone_var.get())
        self.config.save()
        self.do_convert()

    def _fill(self, text: str) -> None:
        self.input_var.set(text)
        self.do_convert()

    def fill_now(self) -> None:
        """填入当前时间而不是 now 字面量，方便在此基础上直接微调。"""
        self._fill(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def _sync_ts_buttons(self) -> None:
        """只有输入确实是时间戳时，对应的换算按钮才可用。

        当前时间、日期字符串这类输入没有"秒/毫秒"的概念，按钮置灰避免误点。
        """
        if not hasattr(self, "btn_s_to_ms"):
            return
        digits = self.input_var.get().strip().lstrip("+-")
        numeric = digits.isdigit()
        self.btn_s_to_ms.set_enabled(numeric and len(digits) == 10)
        self.btn_ms_to_s.set_enabled(numeric and len(digits) == 13)

    def do_s_to_ms(self) -> None:
        text = self.input_var.get().strip()
        if not (text.lstrip("+-").isdigit() and len(text.lstrip("+-")) == 10):
            self.status("请输入 10 位秒级时间戳", "err")
            return
        self._fill(text + "000")

    def do_ms_to_s(self) -> None:
        text = self.input_var.get().strip()
        if not (text.isdigit() and len(text) == 13):
            self.status("请输入 13 位毫秒级时间戳", "err")
            return
        self._fill(text[:-3])

    def _zone_offset(self):
        """必须在主线程调用，Tk 变量不能在工作线程里读取。"""
        return ZONE_OFFSETS.get(self.zone_var.get(), "local")

    def _copy_with_pattern(self, pattern: str) -> None:
        text = self.input_var.get().strip()
        offset = self._zone_offset()
        if not text:
            self.status("请输入时间戳或日期时间", "err")
            return

        def work() -> str:
            dt = tu.parse_input(text, tu.resolve_zone(offset))
            return dt.strftime(pattern)

        self.run_async(work, lambda value: self.copy(value, f"已复制：{value}"))
        self.entry.focus_set()

    # ------------------------------------------------------------ 结果
    def _build_result(self, parent: tk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(parent, columns=("name", "value"), show="headings")
        self.tree.heading("name", text="项目")
        self.tree.heading("value", text="值")
        self.tree.column("name", width=theme.sp(150), anchor="w", stretch=False)
        self.tree.column("value", width=theme.sp(520), anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew")

        bar = ttk.Scrollbar(parent, orient="vertical", command=self.tree.yview)
        bar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=bar.set)
        self.tree.tag_configure("zone", foreground=PALETTE["dim"])
        self.tree.bind("<Double-1>", self._copy_selected)
        self.tree.bind("<Return>", self._copy_selected)

    def _copy_selected(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        values = self.tree.item(selection[0], "values")
        if len(values) >= 2:
            self.copy(str(values[1]), f"已复制：{values[1]}")

    def do_convert(self) -> None:
        text = self.input_var.get().strip()
        if not text:
            self.status("请输入时间戳或日期时间", "err")
            self.entry.focus_set()
            return
        offset = self._zone_offset()

        def work():
            zone = tu.resolve_zone(offset)
            return tu.describe(text, zone), tu.convert_to_zones(text, zone)

        def render(payload) -> None:
            items, zones = payload
            self.tree.delete(*self.tree.get_children())
            for name, value in items:
                self.tree.insert("", "end", values=(name, value))
            for name, value in zones:
                self.tree.insert("", "end", values=(f"· {name}", value), tags=("zone",))
            self.status(f"解析成功 · {len(items)} 项", "ok")

        self.run_async(work, render, busy=[self.btn_convert])

    # ------------------------------------------------------------ 生命周期
    def on_show(self) -> None:
        if self.auto_var.get():
            self._start_tick()
        self.entry.focus_set()

    def on_hide(self) -> None:
        self._stop_tick()
