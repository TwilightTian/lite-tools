#!/usr/bin/env python3
"""核心逻辑自检，不依赖界面。

    python selftest.py
"""

from __future__ import annotations

import json
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.core import codegen as C  # noqa: E402
from app.core import env_utils as E  # noqa: E402
from app.core import json_utils as J  # noqa: E402
from app.core import net_utils as N  # noqa: E402
from app.core import time_utils as T  # noqa: E402

FAILURES: list[str] = []

JAVA_SOURCE = """
package com.demo;

import java.math.BigDecimal;
import java.util.Date;
import java.util.List;
import java.util.Map;

public class Order {
    private String orderNo;
    private Long userId;
    private Integer status;
    private boolean paid;
    private BigDecimal amount;
    private Date createTime;
    private LocalDateTime updateTime;
    private String[] tags;
    private List<OrderItem> items;
    private Map<String, Object> extend;

    public String getOrderNo() { String tmp = "x;y"; return tmp; }
    public void setOrderNo(String orderNo) { this.orderNo = orderNo; }

    public static class OrderItem {
        private String skuName;
        private Integer quantity;
    }
}
"""

JSON_SAMPLE = (
    '{"orderNo":"A1","userId":1,"amount":9.5,"vip":true,"big":99999999999,'
    '"user_info":{"mobile":"138"},"items":[{"skuName":"x","quantity":1}],"tags":["a"]}'
)


def expect(name: str, actual, wanted) -> None:
    if actual == wanted:
        print(f"  [ok] {name}")
    else:
        FAILURES.append(name)
        print(f"  [FAIL] {name}\n         实际: {actual!r}\n         期望: {wanted!r}")


def check(name: str, fn) -> None:
    try:
        fn()
        print(f"  [ok] {name}")
    except Exception as exc:  # noqa: BLE001
        FAILURES.append(name)
        print(f"  [FAIL] {name}: {type(exc).__name__}: {exc}")


def expect_raise(fn, exc_type, contains: str) -> None:
    try:
        fn()
    except exc_type as exc:
        assert contains in str(exc), f"错误信息缺少 {contains!r}：{exc}"
        return
    raise AssertionError(f"没有抛出 {exc_type.__name__}")


def check_java_to_json() -> None:
    data = json.loads(C.java_to_json(JAVA_SOURCE, "Order"))
    assert set(data) == {"orderNo", "userId", "status", "paid", "amount", "createTime",
                         "updateTime", "tags", "items", "extend"}, f"字段不符：{list(data)}"
    assert data["items"][0]["skuName"] == "", "嵌套类字段未展开"
    assert data["extend"] == {}, "Map<String,Object> 应输出空对象"
    assert data["paid"] is True and data["userId"] == 0, "默认值不正确"


def check_json_to_java() -> None:
    text = C.json_to_java(JSON_SAMPLE, "OrderResp", "com.x.model")
    assert "public class OrderResp {" in text, "缺少根类"
    assert "public static class UserInfo {" in text, "缺少内部类"
    assert '@JsonProperty("user_info")' in text, "缺少 Jackson 注解"
    assert "private List<Item> items;" in text, "集合元素类型应按字段名单数化命名"
    assert "private Long big;" in text, "大整数应为 Long"
    assert "private BigDecimal amount;" in text, "小数应为 BigDecimal"
    assert "private Boolean vip;" in text, "布尔应为包装类型"


LENIENT_CASES = [
    ("{'a': 1}", {"a": 1}),
    ("{a: 1, b: 2}", {"a": 1, "b": 2}),
    ("[1, 2, 3,]", [1, 2, 3]),
    ('{"a": 1,}', {"a": 1}),
    ('// 注释\n{"a": 1}', {"a": 1}),
    ('/* 块注释 */ {"a": 1}', {"a": 1}),
    ('{"a": True, "b": False, "c": None}', {"a": True, "b": False, "c": None}),
    ('{"t": "a {b: c}"}', {"t": "a {b: c}"}),
    ("""{"a": 'say "hi"'}""", {"a": 'say "hi"'}),
    ('{"a": [1, 2,], "b": {"c": 3,},}', {"a": [1, 2], "b": {"c": 3}}),
    ('{ key : "值" }', {"key": "值"}),
]


def check_lenient() -> None:
    for source, expected in LENIENT_CASES:
        actual = J.loads(source, lenient=True)
        assert actual == expected, f"{source!r} 解析为 {actual!r}，期望 {expected!r}"
    # 严格模式下同样的输入必须报错
    for source, _expected in LENIENT_CASES[:5]:
        try:
            J.loads(source)
        except J.JsonError:
            continue
        raise AssertionError(f"{source!r} 在严格模式下不应解析成功")


def check_lenient_no_false_positive() -> None:
    """规范内容在宽松模式下不应被改动。"""
    source = '{"a": "b,c", "d": [1, 2]}'
    obj, fixes = J.loads_ex(source, lenient=True)
    assert obj == {"a": "b,c", "d": [1, 2]}, f"解析结果错误：{obj!r}"
    assert fixes == [], f"不应产生修复项：{fixes}"


def check_local_ip() -> None:
    ip = N.primary_ip()
    assert ip and ip.count(".") == 3, f"IP 异常：{ip}"
    assert N.local_addresses(), "没有获取到网卡地址"


def check_localhost_port() -> None:
    ok, message = N.tcp_check("127.0.0.1", 1, 0.5)
    assert ok is False, "端口 1 不应该开放"
    assert message, "缺少说明信息"


def main() -> int:
    print("== JSON ==")
    expect("格式化并按 key 排序", J.format_text('{"b":1,"a":2}', sort_keys=True),
           '{\n  "a": 2,\n  "b": 1\n}')
    expect("压缩", J.minify('{ "a" : [1, 2] }'), '{"a":[1,2]}')
    expect("转义", J.escape_string('a"b\nc'), '"a\\"b\\nc"')
    expect("反转义（无外层引号）", J.unescape_string(r'{\"a\":1}'), '{"a":1}')
    expect("中文转义", J.to_ascii_escape("中文"), '"\\u4e2d\\u6587"')
    expect("路径取值", J.query({"a": {"b": [1, 2, 3]}}, "a.b[1]"), 2)
    expect("校验信息", J.validate("[1,2,3]"), "合法 JSON · 根为数组 · 3 个元素")
    check("非法 JSON 报错带行列",
          lambda: expect_raise(lambda: J.loads('{"a":}'), J.JsonError, "第 1 行"))
    check("宽松模式修复常见错误", check_lenient)
    check("宽松模式不误伤规范内容", check_lenient_no_false_positive)

    print("== 时间 ==")
    expect("秒级时间戳", dict(T.describe("1712300000"))["Unix 秒"], "1712300000")
    expect("毫秒级时间戳", dict(T.describe("1712300000000"))["Unix 秒"], "1712300000")
    expect("日期字符串", dict(T.describe("2024-03-05 12:30:00"))["Unix 秒"], "1709613000")
    expect("yyyyMMdd 格式", dict(T.describe("20240305"))["日期"], "2024-03-05")
    expect("时区换算项数", len(T.convert_to_zones("1712300000")), len(T.COMMON_ZONES))
    expect("批量转换", len(T.batch_convert("1712300000\n2024-03-05")), 2)

    print("== 启动变量 ==")
    expect("IDEA -> Linux", E.convert('A=1;B="x;y";C=', "IDEA", "Linux export"),
           "export A=1\nexport B='x;y'\nexport C=")
    expect("Linux -> IDEA", E.convert("export A=1\nexport B='hello world'", "Linux export", "IDEA"),
           'A=1;B="hello world"')
    expect("JSON -> .env", E.convert('{"A":"1","B":"2"}', "JSON", ".env"), "A=1\nB=2")
    expect("docker -e 解析", E.parse("-e A=1 -e B=2", "docker -e"), [("A", "1"), ("B", "2")])
    # 同一行多条 export
    expect("同行多条 export",
           E.convert("export A=1;export B=2", "Linux export", "IDEA"), "A=1;B=2")
    expect("&& 连接", E.parse("A=1 && B=2", "Linux export"), [("A", "1"), ("B", "2")])
    # 变量引用必须保留展开能力，不能被单引号屏蔽
    expect("$ 变量保留展开",
           E.convert('A="$PATH:/opt/bin"', "IDEA", "Linux export"),
           'export A="$PATH:/opt/bin"')
    expect("$ 变量反向",
           E.convert('export A="$PATH:/opt"', "Linux export", "IDEA"),
           'A=$PATH:/opt')
    # 转义还原
    expect("双引号内转义还原",
           E.convert('MSG="say \\"hi\\""', "IDEA", "Linux export"),
           "export MSG='say \"hi\"'")
    expect("shell 引号拼接", E.parse("export A='it'\\''s'", "Linux export"), [("A", "it's")])
    expect("空值不加引号", E.convert("A=", "IDEA", "Linux export"), "export A=")
    expect("等号保留在值里", E.parse("A=hello=world", "IDEA"), [("A", "hello=world")])

    print("== Java <-> JSON ==")
    expect("识别到的类", C.list_classes(JAVA_SOURCE), ["Order", "OrderItem"])
    check("Java -> JSON", check_java_to_json)
    check("JSON -> Java", check_json_to_java)

    print("== 网络 ==")
    expect("端口解析", N.parse_ports("80,443, 8000-8003"), [80, 443, 8000, 8001, 8002, 8003])
    check("本机 IP", check_local_ip)
    check("回环端口探测", check_localhost_port)

    print()
    if FAILURES:
        print(f"失败 {len(FAILURES)} 项：{', '.join(FAILURES)}")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
