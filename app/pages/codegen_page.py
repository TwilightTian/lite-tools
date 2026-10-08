"""JSON 生成页：Java 实体类 <-> JSON 双向转换。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .. import theme
from ..core import codegen as cg
from ..theme import PALETTE
from ..widgets import Card, FlowFrame, SplitPanes, Tabs, button, check_box
from .base import Page

JAVA_SAMPLE = '''package com.demo.model;

import java.math.BigDecimal;
import java.util.Date;
import java.util.List;
import java.util.Map;

public class Order {

    /** 订单号 */
    private String orderNo;
    private Long userId;
    private Integer status;
    private Boolean paid;
    private BigDecimal amount;
    private Date createTime;
    private List<OrderItem> items;
    private Map<String, Object> extend;

    public String getOrderNo() {
        return orderNo;
    }

    public static class OrderItem {
        private String skuName;
        private Integer quantity;
        private BigDecimal price;
    }
}
'''

JSON_SAMPLE = '''{
  "orderNo": "SO20240305001",
  "userId": 10086,
  "status": 1,
  "paid": true,
  "amount": 199.5,
  "createTime": "2024-03-05 12:30:00",
  "user_info": {
    "nickName": "张三",
    "mobile": "13800000000"
  },
  "items": [
    {
      "skuName": "椅子",
      "quantity": 2,
      "price": 99.75
    }
  ],
  "tags": ["vip", "new"]
}
'''


class CodegenPage(Page):
    title = "JSON 生成"
    desc = "解析 Java 实体类生成 JSON 样例，或由 JSON 反向生成 POJO"

    def build(self) -> None:
        self.tabs = Tabs(self.body, [("java", "Java → JSON"), ("json", "JSON → Java")],
                         parent_bg=PALETTE["bg"])
        self.tabs.pack(fill="both", expand=True)

        self._build_java_tab(self.tabs.page("java"))
        self._build_json_tab(self.tabs.page("json"))

    # ================================================================ Java -> JSON
    def _build_java_tab(self, parent: tk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        bar = Card(parent, padding=(12, 10), stretch=False)
        bar.grid(row=0, column=0, sticky="ew")
        flow = FlowFrame(bar.content, parent_bg=PALETTE["card"])
        flow.pack(fill="x")

        class_box = tk.Frame(flow, background=PALETTE["card"])
        tk.Label(class_box, text="根类名", background=PALETTE["card"],
                 foreground=PALETTE["text"], font=theme.ui_font).pack(side="left",
                                                                     padx=(0, theme.sp(6)))
        self.java_class_var = tk.StringVar()
        self.java_class_combo = ttk.Combobox(class_box, textvariable=self.java_class_var,
                                             state="readonly", width=16, values=[])
        self.java_class_combo.pack(side="left")
        flow.add(class_box)

        depth_box = tk.Frame(flow, background=PALETTE["card"])
        tk.Label(depth_box, text="嵌套深度", background=PALETTE["card"],
                 foreground=PALETTE["text"], font=theme.ui_font).pack(side="left",
                                                                     padx=(0, theme.sp(6)))
        self.depth_var = tk.StringVar(value=str(self.config.get("codegen.depth", 3)))
        ttk.Combobox(depth_box, textvariable=self.depth_var, state="readonly", width=4,
                     values=["1", "2", "3", "4", "5"]).pack(side="left")
        flow.add(depth_box)

        date_box = tk.Frame(flow, background=PALETTE["card"])
        tk.Label(date_box, text="日期示例", background=PALETTE["card"],
                 foreground=PALETTE["text"], font=theme.ui_font).pack(side="left",
                                                                     padx=(0, theme.sp(6)))
        self.date_var = tk.StringVar()
        ttk.Entry(date_box, textvariable=self.date_var, width=20).pack(side="left")
        flow.add(date_box)

        self.btn_generate = button(flow, "生成 JSON", self.do_java_to_json, kind="primary")
        flow.add(self.btn_generate)
        flow.add(button(flow, "刷新类列表", self.refresh_classes))
        flow.add(button(flow, "示例", self.fill_java_sample, kind="ghost"))
        flow.add(button(flow, "复制结果", self.copy_java_result, kind="ghost"))

        panes = SplitPanes(parent)
        panes.grid(row=1, column=0, sticky="nsew", pady=(theme.sp(8), 0))

        left = Card(panes.left, title="Java 源码", min_height=300)
        panes.add(left, "left")
        self.java_source = self.make_code_area(left.content, height=18,
                                               line_numbers=True, wrap=False)
        self.java_source.pack(fill="both", expand=True)

        right = Card(panes.right, title="生成的 JSON", min_height=300)
        panes.add(right, "right")
        self.java_result = self.make_code_area(right.content, height=18, editable=False,
                                               line_numbers=True, wrap=False)
        self.java_result.pack(fill="both", expand=True)

    def fill_java_sample(self) -> None:
        self.java_source.set(JAVA_SAMPLE)
        self.refresh_classes()
        self.do_java_to_json()

    def refresh_classes(self) -> None:
        source = self.java_source.get()
        if not source.strip():
            self.status("请先粘贴 Java 源码", "err")
            return
        names = cg.list_classes(source)
        self.java_class_combo.configure(values=names)
        if names and self.java_class_var.get() not in names:
            self.java_class_var.set(names[0])
        if names:
            self.status(f"识别到 {len(names)} 个类：{', '.join(names)}", "ok")
        else:
            self.status("没有解析到 class / interface / enum 定义", "err")

    def do_java_to_json(self) -> None:
        source = self.java_source.get()
        if not source.strip():
            self.status("请先粘贴 Java 源码", "err")
            return
        if not self.java_class_var.get():
            self.refresh_classes()

        # Tk 变量必须在主线程读取，线程里只使用普通值
        root_name = self.java_class_var.get() or None
        depth = int(self.depth_var.get() or 3)
        date_sample = self.date_var.get().strip() or None
        self.config.set("codegen.depth", depth)
        self.config.save()

        def work() -> str:
            return cg.java_to_json(source, root=root_name, depth=depth,
                                   date_sample=date_sample)

        def render(result: str) -> None:
            self.java_result.set(result)
            self.status(f"已生成 JSON · {len(result)} 字符", "ok")

        self.run_async(work, render, busy=[self.btn_generate])

    def copy_java_result(self) -> None:
        text = self.java_result.get()
        if not text:
            self.status("还没有生成结果", "err")
            return
        self.copy(text)

    # ================================================================ JSON -> Java
    def _build_json_tab(self, parent: tk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        bar = Card(parent, padding=(12, 10), stretch=False)
        bar.grid(row=0, column=0, sticky="ew")
        flow = FlowFrame(bar.content, parent_bg=PALETTE["card"])
        flow.pack(fill="x")

        class_box = tk.Frame(flow, background=PALETTE["card"])
        tk.Label(class_box, text="类名", background=PALETTE["card"],
                 foreground=PALETTE["text"], font=theme.ui_font).pack(side="left",
                                                                     padx=(0, theme.sp(6)))
        self.class_var = tk.StringVar(value=str(self.config.get("codegen.class_name", "Root")))
        ttk.Entry(class_box, textvariable=self.class_var, width=16).pack(side="left")
        flow.add(class_box)

        package_box = tk.Frame(flow, background=PALETTE["card"])
        tk.Label(package_box, text="包名", background=PALETTE["card"],
                 foreground=PALETTE["text"], font=theme.ui_font).pack(side="left",
                                                                     padx=(0, theme.sp(6)))
        self.package_var = tk.StringVar(value=str(self.config.get("codegen.package", "")))
        ttk.Entry(package_box, textvariable=self.package_var, width=22).pack(side="left")
        flow.add(package_box)

        self.lombok_var = tk.BooleanVar(value=bool(self.config.get("codegen.use_lombok", True)))
        self.jackson_var = tk.BooleanVar(value=bool(self.config.get("codegen.use_jackson", True)))
        self.boxed_var = tk.BooleanVar(value=bool(self.config.get("codegen.boxed", True)))
        for text, variable in (("Lombok @Data", self.lombok_var),
                               ("Jackson 注解", self.jackson_var),
                               ("包装类型", self.boxed_var)):
            flow.add(check_box(flow, text, variable, parent_bg=PALETTE["card"]))

        self.btn_build = button(flow, "生成 Java", self.do_json_to_java, kind="primary")
        flow.add(self.btn_build)
        flow.add(button(flow, "示例", self.fill_json_sample, kind="ghost"))
        flow.add(button(flow, "复制结果", self.copy_json_result, kind="ghost"))

        panes = SplitPanes(parent)
        panes.grid(row=1, column=0, sticky="nsew", pady=(theme.sp(8), 0))

        left = Card(panes.left, title="JSON 样本", min_height=300)
        panes.add(left, "left")
        self.json_source = self.make_code_area(left.content, height=18,
                                               line_numbers=True, wrap=False)
        self.json_source.pack(fill="both", expand=True)

        right = Card(panes.right, title="生成的 Java 类", min_height=300)
        panes.add(right, "right")
        self.json_result = self.make_code_area(right.content, height=18, editable=False,
                                               line_numbers=True, wrap=False)
        self.json_result.pack(fill="both", expand=True)

    def fill_json_sample(self) -> None:
        self.json_source.set(JSON_SAMPLE)
        self.do_json_to_java()

    def do_json_to_java(self) -> None:
        text = self.json_source.get()
        if not text.strip():
            self.status("请先粘贴 JSON 样本", "err")
            return

        class_name = self.class_var.get() or "Root"
        package = self.package_var.get()
        use_lombok = bool(self.lombok_var.get())
        use_jackson = bool(self.jackson_var.get())
        boxed = bool(self.boxed_var.get())

        self.config.set("codegen.class_name", self.class_var.get())
        self.config.set("codegen.package", package)
        self.config.set("codegen.use_lombok", use_lombok)
        self.config.set("codegen.use_jackson", use_jackson)
        self.config.set("codegen.boxed", boxed)
        self.config.save()

        def work() -> str:
            return cg.json_to_java(text, class_name=class_name, package=package,
                                   use_lombok=use_lombok, use_jackson=use_jackson,
                                   boxed=boxed)

        def render(result: str) -> None:
            self.json_result.set(result)
            self.status(f"已生成 Java 类 · {len(result)} 字符", "ok")

        self.run_async(work, render, busy=[self.btn_build])

    def copy_json_result(self) -> None:
        text = self.json_result.get()
        if not text:
            self.status("还没有生成结果", "err")
            return
        self.copy(text)

    # ------------------------------------------------------------ 生命周期
    def on_show(self) -> None:
        if not self.java_source.get():
            self.java_source.set(JAVA_SAMPLE)
            self.refresh_classes()
        if not self.json_source.get():
            self.json_source.set(JSON_SAMPLE)
