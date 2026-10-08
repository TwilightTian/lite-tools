"""网络工具页：IP 速查 / ping / DNS 解析与缓存清理 / 端口连通检测。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .. import theme
from ..core import net_utils as nu
from ..theme import PALETTE
from ..widgets import Card, FlowFrame, SplitPanes, Tabs, button
from .base import Page

DEFAULT_PORTS = "80,443,8080,3306,6379"


class NetPage(Page):
    title = "网络工具"
    desc = "本机 IP · 公网 IP · DNS · ping · 端口连通"

    def build(self) -> None:
        self.tabs = Tabs(
            self.body,
            [("local", "本机与 DNS"), ("ping", "Ping"), ("port", "端口检测")],
            parent_bg=PALETTE["bg"],
        )
        self.tabs.pack(fill="both", expand=True)

        self._build_local_tab(self.tabs.page("local"))
        self._build_ping_tab(self.tabs.page("ping"))
        self._build_port_tab(self.tabs.page("port"))

    # ============================================================ 本机与 DNS
    def _build_local_tab(self, parent: tk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        top = SplitPanes(parent, min_column=320, stretch=False)
        top.grid(row=0, column=0, sticky="ew")

        info = Card(top.left, title="本机信息", padding=(14, 12), stretch=False)
        top.add(info, "left")

        self.host_var = tk.StringVar(value="—")
        self.local_ip_var = tk.StringVar(value="—")
        self.public_ip_var = tk.StringVar(value="—")
        for label, variable in (("主机名", self.host_var),
                                ("本机 IP", self.local_ip_var),
                                ("公网 IP", self.public_ip_var)):
            line = tk.Frame(info.content, background=PALETTE["card"])
            line.pack(fill="x", pady=theme.sp(1))
            tk.Label(line, text=label, background=PALETTE["card"],
                     foreground=PALETTE["dim"], font=theme.ui_small,
                     width=8, anchor="w").pack(side="left")
            tk.Label(line, textvariable=variable, background=PALETTE["card"],
                     foreground=PALETTE["text"], font=theme.ui_font,
                     anchor="w").pack(side="left")

        actions = FlowFrame(info.content, parent_bg=PALETTE["card"])
        actions.pack(fill="x", pady=(theme.sp(9), 0))
        self.btn_refresh = button(actions, "刷新本机信息", self.refresh_local,
                                  parent_bg=PALETTE["card"])
        actions.add(self.btn_refresh)
        self.btn_public = button(actions, "获取公网 IP", self.fetch_public_ip,
                                 kind="primary", parent_bg=PALETTE["card"])
        actions.add(self.btn_public)

        queried = Card(top.right, title="IP 归属地", padding=(14, 12), stretch=False)
        top.add(queried, "right")
        line = tk.Frame(queried.content, background=PALETTE["card"])
        line.pack(fill="x")
        tk.Label(line, text="查询 IP", background=PALETTE["card"],
                 foreground=PALETTE["text"], font=theme.ui_font).pack(side="left",
                                                                     padx=(0, theme.sp(6)))
        self.ip_query_var = tk.StringVar()
        entry = ttk.Entry(line, textvariable=self.ip_query_var)
        entry.pack(side="left", fill="x", expand=True)
        entry.bind("<Return>", lambda _e: self.lookup_ip_info())
        button(line, "查询", self.lookup_ip_info, kind="ghost",
               parent_bg=PALETTE["card"]).pack(side="left", padx=(theme.sp(6), 0))

        tk.Label(queried.content, text="留空则查询本机公网 IP", background=PALETTE["card"],
                 foreground=PALETTE["dim"], font=theme.ui_small, anchor="w").pack(
            anchor="w", pady=(theme.sp(6), 0))
        self.ip_result = self.make_code_area(queried.content, height=5, editable=False,
                                             wrap=True)
        self.ip_result.pack(fill="both", expand=True, pady=(theme.sp(6), 0))

        cards = Card(parent, title="DNS 与网卡", min_height=190)
        cards.grid(row=1, column=0, sticky="nsew", pady=(theme.sp(10), 0))
        cards.content.rowconfigure(1, weight=1)
        cards.content.columnconfigure(0, weight=1)

        dns_flow = FlowFrame(cards.content, parent_bg=PALETTE["card"])
        dns_flow.grid(row=0, column=0, sticky="ew")
        dns_box = tk.Frame(dns_flow, background=PALETTE["card"])
        tk.Label(dns_box, text="域名解析", background=PALETTE["card"],
                 foreground=PALETTE["text"], font=theme.ui_font).pack(side="left",
                                                                     padx=(0, theme.sp(6)))
        self.dns_var = tk.StringVar(value="www.baidu.com")
        dns_entry = ttk.Entry(dns_box, textvariable=self.dns_var, width=26)
        dns_entry.pack(side="left")
        dns_entry.bind("<Return>", lambda _e: self.do_resolve())
        dns_flow.add(dns_box)
        self.btn_resolve = button(dns_flow, "解析", self.do_resolve, parent_bg=PALETTE["card"])
        dns_flow.add(self.btn_resolve)
        self.btn_flush = button(dns_flow, "清理 DNS 缓存", self.do_flush_dns, kind="primary",
                                parent_bg=PALETTE["card"])
        dns_flow.add(self.btn_flush)

        self.dns_result = tk.Label(
            cards.content, text="", background=PALETTE["card"],
            foreground=PALETTE["dim"], font=theme.ui_small, anchor="w", justify="left",
            wraplength=theme.sp(880),
        )
        self.dns_result.grid(row=0, column=1, sticky="w", padx=(theme.sp(14), 0))

        table = tk.Frame(cards.content, background=PALETTE["card"])
        table.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(theme.sp(9), 0))
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)

        self.adapter_tree = ttk.Treeview(
            table, columns=("iface", "ip", "mask", "gateway"), show="headings", height=5
        )
        for key, text, width in (("iface", "网卡", 260), ("ip", "IP 地址", 140),
                                 ("mask", "子网掩码", 140), ("gateway", "默认网关", 140)):
            self.adapter_tree.heading(key, text=text)
            self.adapter_tree.column(key, width=theme.sp(width), anchor="w")
        self.adapter_tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.adapter_tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.adapter_tree.configure(yscrollcommand=scroll.set)

    def refresh_local(self) -> None:
        def work():
            return nu.hostname(), nu.local_addresses()

        def render(payload) -> None:
            host, addresses = payload
            self.host_var.set(host)
            if addresses:
                self.local_ip_var.set(addresses[0].ip)
            self.adapter_tree.delete(*self.adapter_tree.get_children())
            for addr in addresses:
                self.adapter_tree.insert(
                    "", "end",
                    values=(addr.interface, addr.ip, addr.netmask or "-", addr.gateway or "-"),
                )
            self.status(f"已刷新本机信息 · {len(addresses)} 个地址", "ok")

        self.run_async(work, render, busy=[self.btn_refresh])

    def fetch_public_ip(self) -> None:
        api = str(self.config.get("net.public_ip_api", "https://api.ipify.org"))
        timeout = float(self.config.get("net.timeout", 3.0))
        self.status("正在获取公网 IP…")
        self.run_async(
            lambda: nu.public_ip(api, timeout),
            lambda value: (self.public_ip_var.set(value), self.status(f"公网 IP：{value}", "ok")),
            busy=[self.btn_public], progress=True,
        )

    def lookup_ip_info(self) -> None:
        target = self.ip_query_var.get().strip() or self.public_ip_var.get().strip()
        if not target or target == "—":
            self.status("请先输入 IP，或先获取公网 IP", "err")
            return
        timeout = float(self.config.get("net.timeout", 3.0))
        self.status(f"正在查询 {target}…")
        self.run_async(lambda: nu.ip_info(target, timeout), self._show_ip_info, progress=True)

    def _show_ip_info(self, text: str) -> None:
        self.ip_result.set(text)
        self.status("归属地查询完成", "ok")

    def do_resolve(self) -> None:
        host = self.dns_var.get().strip()
        if not host:
            self.status("请输入域名", "err")
            return

        def render(records) -> None:
            text = "    ".join(f"{kind}: {address}" for kind, address in records)
            self.dns_result.configure(text=text)
            self.status(f"{host} 解析到 {len(records)} 条记录", "ok")

        self.run_async(lambda: nu.resolve(host), render, busy=[self.btn_resolve])

    def do_flush_dns(self) -> None:
        self.status("正在清理 DNS 缓存…")
        self.run_async(
            nu.flush_dns,
            lambda output: (
                self.dns_result.configure(text="DNS 缓存已清理"),
                self.status(output.replace("\n", " ")[:120], "ok"),
            ),
            busy=[self.btn_flush], progress=True,
        )

    # ============================================================ Ping
    def _build_ping_tab(self, parent: tk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        bar = Card(parent, padding=(12, 10), stretch=False)
        bar.grid(row=0, column=0, sticky="ew")
        flow = FlowFrame(bar.content, parent_bg=PALETTE["card"])
        flow.pack(fill="x")

        host_box = tk.Frame(flow, background=PALETTE["card"])
        tk.Label(host_box, text="主机/域名", background=PALETTE["card"],
                 foreground=PALETTE["text"], font=theme.ui_font).pack(side="left",
                                                                     padx=(0, theme.sp(6)))
        self.ping_host_var = tk.StringVar(value=str(self.config.get("net.ping_host", "www.baidu.com")))
        entry = ttk.Entry(host_box, textvariable=self.ping_host_var, width=28)
        entry.pack(side="left")
        entry.bind("<Return>", lambda _e: self.do_ping())
        flow.add(host_box)

        count_box = tk.Frame(flow, background=PALETTE["card"])
        tk.Label(count_box, text="次数", background=PALETTE["card"],
                 foreground=PALETTE["text"], font=theme.ui_font).pack(side="left",
                                                                     padx=(0, theme.sp(6)))
        self.ping_count_var = tk.StringVar(value=str(self.config.get("net.ping_count", 4)))
        ttk.Combobox(count_box, textvariable=self.ping_count_var, state="readonly", width=4,
                     values=["2", "4", "6", "10", "20"]).pack(side="left")
        flow.add(count_box)

        self.btn_ping = button(flow, "开始 Ping", self.do_ping, kind="primary")
        flow.add(self.btn_ping)
        flow.add(button(flow, "清空", lambda: self.ping_output.clear(), kind="ghost"))

        self.ping_summary = tk.Label(bar.content, text="", background=PALETTE["card"],
                                     foreground=PALETTE["dim"], font=theme.ui_small,
                                     anchor="w")
        self.ping_summary.pack(anchor="w", pady=(theme.sp(8), 0))

        output = Card(parent, title="输出", min_height=280)
        output.grid(row=1, column=0, sticky="nsew", pady=(theme.sp(10), 0))
        self.ping_output = self.make_code_area(output.content, height=16, editable=False,
                                               wrap=False)
        self.ping_output.pack(fill="both", expand=True)

    def do_ping(self) -> None:
        host = self.ping_host_var.get().strip()
        if not host:
            self.status("请输入主机或域名", "err")
            return
        count = int(self.ping_count_var.get() or 4)
        timeout = float(self.config.get("net.timeout", 3.0))
        self.config.set("net.ping_host", host)
        self.config.set("net.ping_count", count)
        self.config.save()

        self.ping_output.clear()
        self.ping_summary.configure(text=f"正在 ping {host} …")
        self.status(f"正在 ping {host}")

        lines: list[str] = []

        def on_line(line: str) -> None:
            lines.append(line)
            self.ping_output.append(line)

        def on_done(_payload=None) -> None:
            summary = nu.parse_ping_summary(lines)
            self.ping_summary.configure(text=summary or "ping 结束")
            self.status(summary or "ping 结束", "ok")

        self.run_stream(nu.ping(host, count, timeout), on_line, on_done,
                        busy=[self.btn_ping], progress=True)

    # ============================================================ 端口检测
    def _build_port_tab(self, parent: tk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        bar = Card(parent, padding=(12, 10), stretch=False)
        bar.grid(row=0, column=0, sticky="ew")
        flow = FlowFrame(bar.content, parent_bg=PALETTE["card"])
        flow.pack(fill="x")

        host_box = tk.Frame(flow, background=PALETTE["card"])
        tk.Label(host_box, text="主机/IP", background=PALETTE["card"],
                 foreground=PALETTE["text"], font=theme.ui_font).pack(side="left",
                                                                     padx=(0, theme.sp(6)))
        self.port_host_var = tk.StringVar(value="127.0.0.1")
        ttk.Entry(host_box, textvariable=self.port_host_var, width=20).pack(side="left")
        flow.add(host_box)

        port_box = tk.Frame(flow, background=PALETTE["card"])
        tk.Label(port_box, text="端口", background=PALETTE["card"],
                 foreground=PALETTE["text"], font=theme.ui_font).pack(side="left",
                                                                     padx=(0, theme.sp(6)))
        self.port_list_var = tk.StringVar(value=DEFAULT_PORTS)
        port_entry = ttk.Entry(port_box, textvariable=self.port_list_var, width=26)
        port_entry.pack(side="left")
        port_entry.bind("<Return>", lambda _e: self.do_check_ports())
        flow.add(port_box)

        self.btn_check = button(flow, "开始检测", self.do_check_ports, kind="primary")
        flow.add(self.btn_check)
        flow.add(button(flow, "清空", self.clear_ports, kind="ghost"))

        tk.Label(bar.content, text="端口写法：80,443,8000-8010（相当于 telnet 的连通性探测）",
                 background=PALETTE["card"], foreground=PALETTE["dim"],
                 font=theme.ui_small, anchor="w").pack(anchor="w", pady=(theme.sp(8), 0))

        card = Card(parent, title="检测结果", min_height=280)
        card.grid(row=1, column=0, sticky="nsew", pady=(theme.sp(10), 0))
        card.content.columnconfigure(0, weight=1)
        card.content.rowconfigure(0, weight=1)

        self.port_tree = ttk.Treeview(card.content, columns=("port", "state", "detail"),
                                      show="headings", height=12)
        self.port_tree.heading("port", text="端口")
        self.port_tree.heading("state", text="状态")
        self.port_tree.heading("detail", text="说明")
        self.port_tree.column("port", width=theme.sp(80), anchor="w", stretch=False)
        self.port_tree.column("state", width=theme.sp(80), anchor="w", stretch=False)
        self.port_tree.column("detail", width=theme.sp(420), anchor="w")
        self.port_tree.tag_configure("open", foreground=PALETTE["ok"])
        self.port_tree.tag_configure("closed", foreground=PALETTE["err"])
        self.port_tree.grid(row=0, column=0, sticky="nsew")
        bar2 = ttk.Scrollbar(card.content, orient="vertical", command=self.port_tree.yview)
        bar2.grid(row=0, column=1, sticky="ns")
        self.port_tree.configure(yscrollcommand=bar2.set)
        self.port_tree.bind("<Double-1>", self._copy_port_result)

    def _copy_port_result(self, _event=None) -> None:
        selection = self.port_tree.selection()
        if not selection:
            return
        values = self.port_tree.item(selection[0], "values")
        self.copy(f"{self.port_host_var.get()}:{values[0]}", f"已复制 {values[0]} 端口")

    def clear_ports(self) -> None:
        self.port_tree.delete(*self.port_tree.get_children())
        self.status("已清空检测结果")

    def do_check_ports(self) -> None:
        host = self.port_host_var.get().strip()
        ports = nu.parse_ports(self.port_list_var.get())
        if not host:
            self.status("请输入主机或 IP", "err")
            return
        if not ports:
            self.status("请输入有效端口，如 80,443,8000-8010", "err")
            return

        self.port_tree.delete(*self.port_tree.get_children())
        timeout = float(self.config.get("net.timeout", 3.0))
        self.status(f"正在检测 {host} 的 {len(ports)} 个端口…")
        done = {"count": 0}

        def produce():
            for port in ports:
                ok, message = nu.tcp_check(host, port, timeout)
                done["count"] += 1
                yield port, ok, message

        def on_line(item) -> None:
            port, ok, message = item
            self.port_tree.insert("", "end", values=(port, "开放" if ok else "不通", message),
                                  tags=("open" if ok else "closed",))
            self.status(f"检测中 {done['count']}/{len(ports)}…")

        def on_done(_payload=None) -> None:
            opened = sum(
                1 for item in self.port_tree.get_children()
                if self.port_tree.item(item, "values")[1] == "开放"
            )
            self.status(f"检测完成 · 开放 {opened} / 共 {len(ports)}", "ok")

        self.run_stream(produce(), on_line, on_done, busy=[self.btn_check],
                        progress=True, total=len(ports))

    # ============================================================ 生命周期
    def on_show(self) -> None:
        if self.host_var.get() == "—":
            self.refresh_local()
