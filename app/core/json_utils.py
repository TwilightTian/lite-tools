"""JSON 文本处理：格式化 / 压缩 / 转义 / 反转义 / 排序 / 校验 / 取值。

宽松模式（lenient）会尝试修复没有歧义的常见写法错误：
注释、单引号字符串、未加引号的键、尾随逗号、Python 风格 True/False/None、
字符串内的裸换行、BOM，修复内容通过 `report` 列表回传。
"""

from __future__ import annotations

import json
import re
from typing import Any

_LITERALS = (("True", "true"), ("False", "false"), ("None", "null"))


class JsonError(ValueError):
    """带行列定位的 JSON 解析错误。"""

    def __init__(self, message: str, doc: str = "", pos: int | None = None):
        super().__init__(message)
        self.message = message
        self.pos = pos
        if pos is None or not doc:
            self.line = self.col = None
        else:
            self.line = doc.count("\n", 0, pos) + 1
            self.col = pos - (doc.rfind("\n", 0, pos) + 1) + 1

    def __str__(self) -> str:
        if self.line:
            return f"{self.message}（第 {self.line} 行，第 {self.col} 列）"
        return self.message


# ================================================================ 解析
# Python json 模块的报错信息是英文的，这里换成更直观的中文提示
_ERROR_HINTS = (
    ("Expecting value", "此处需要一个合法的 JSON 值（字符串、数字、对象、数组或 null）"),
    ("Expecting property name enclosed in double quotes", "对象的键必须用双引号包裹"),
    ("Expecting ':' delimiter", "键与值之间缺少冒号"),
    ("Expecting ',' delimiter", "此处缺少逗号或多余的字符"),
    ("Unterminated string starting at", "字符串没有闭合"),
    ("Invalid control character at", "字符串中包含未转义的控制字符（如换行）"),
    ("Invalid \\escape", "包含非法的反斜杠转义序列"),
    ("Extra data", "合法内容之后还有多余的数据"),
    ("Invalid \\uXXXX escape", "包含非法的 \\uXXXX 转义"),
)


def _friendly(message: str) -> str:
    for prefix, translated in _ERROR_HINTS:
        if message.startswith(prefix):
            return translated
    return message


def _strict_loads(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise JsonError(_friendly(exc.msg), text, exc.pos) from None


def loads(text: str, lenient: bool = False) -> Any:
    """解析 JSON；lenient 为真时先尝试自动修复不规范写法。"""
    obj, _fixes = loads_ex(text, lenient)
    return obj


def loads_ex(text: str, lenient: bool = False) -> tuple[Any, list[str]]:
    """解析 JSON，同时返回宽松模式下的修复说明。"""
    source = (text or "").strip()
    if not source:
        raise JsonError("内容为空")
    if not lenient:
        return _strict_loads(source), []

    try:
        return _strict_loads(source), []
    except JsonError:
        pass

    normalized, fixes = normalize(source)
    if normalized == source:
        return _strict_loads(source), []
    try:
        return _strict_loads(normalized), fixes
    except JsonError as exc:
        raise JsonError(
            f"自动修复后仍无法解析：{exc.message}", source
        ) from None


def normalize(text: str) -> tuple[str, list[str]]:
    """把常见的不规范 JSON 写法规范化为标准 JSON 文本。

    只在字符串之外做替换，不会破坏字符串内容。
    """
    if text.startswith("\ufeff"):
        text = text[1:]

    out: list[str] = []
    fixes: list[str] = []
    stack: list[str] = []
    i, n = 0, len(text)
    in_string = False
    quote = ""

    while i < n:
        ch = text[i]

        # ---------------------------------------------------- 字符串内部
        if in_string:
            if ch == "\\":
                if i + 1 < n:
                    nxt = text[i + 1]
                    if nxt == "'":
                        out.append("'")
                    elif nxt == '"':
                        out.append('\\"')
                    else:
                        out.append(ch + nxt)
                    i += 2
                    continue
                out.append(ch)
                i += 1
                continue
            if ch == quote:
                in_string = False
                out.append('"')
                i += 1
                continue
            if quote == "'" and ch == '"':
                out.append('\\"')
                i += 1
                continue
            if ch in "\r\n":
                out.append("\\n")
                if ch == "\r" and i + 1 < n and text[i + 1] == "\n":
                    i += 1
                i += 1
                _note(fixes, "字符串内的换行改为 \\n")
                continue
            if ch == "\t":
                out.append("\\t")
                i += 1
                _note(fixes, "字符串内的制表符改为 \\t")
                continue
            out.append(ch)
            i += 1
            continue

        # ---------------------------------------------------- 字符串外部
        if ch in " \t\r\n":
            out.append(ch)
            i += 1
            continue
        if text.startswith("//", i):
            end = text.find("\n", i)
            i = n if end < 0 else end
            _note(fixes, "移除 // 注释")
            continue
        if text.startswith("/*", i):
            end = text.find("*/", i)
            i = n if end < 0 else end + 2
            _note(fixes, "移除 /* */ 注释")
            continue
        if ch in "\"'":
            in_string = True
            quote = ch
            out.append('"')
            i += 1
            if ch == "'":
                _note(fixes, "单引号字符串改为双引号")
            continue
        if ch in "{[":
            stack.append("obj" if ch == "{" else "arr")
            out.append(ch)
            i += 1
            i = _consume_key(text, i, out, fixes)
            continue
        if ch in "}]":
            if stack:
                stack.pop()
            _drop_trailing_comma(out, fixes)
            out.append(ch)
            i += 1
            continue
        if ch == ",":
            out.append(ch)
            i += 1
            if stack and stack[-1] == "obj":
                i = _consume_key(text, i, out, fixes)
            continue
        if ch in "TFN":
            consumed = _consume_literal(text, i, out)
            if consumed:
                _note(fixes, f"{text[i:i + consumed]} 改为 JSON 字面量")
                i += consumed
                continue
        out.append(ch)
        i += 1

    return "".join(out), fixes


def _note(fixes: list[str], message: str) -> None:
    if message not in fixes:
        fixes.append(message)


def _drop_trailing_comma(out: list[str], fixes: list[str]) -> None:
    index = len(out) - 1
    while index >= 0 and not out[index].strip():
        index -= 1
    if index >= 0 and out[index] == ",":
        del out[index]
        _note(fixes, "移除尾随逗号")


def _consume_key(text: str, i: int, out: list[str], fixes: list[str]) -> int:
    """处理对象里紧跟在 `{` 或 `,` 之后的键：给裸标识符补引号。"""
    n = len(text)
    start = i
    while start < n and text[start] in " \t\r\n":
        start += 1
    if start >= n:
        return i
    first = text[start]
    if first in "\"'":
        return i
    if not (first.isalpha() or first in "_$"):
        return i

    end = start
    while end < n and (text[end].isalnum() or text[end] in "_$"):
        end += 1
    colon = end
    while colon < n and text[colon] in " \t\r\n":
        colon += 1
    if colon >= n or text[colon] != ":":
        return i

    out.append(text[i:start])
    out.append('"' + text[start:end] + '"')
    out.append(text[end:colon])
    out.append(":")
    _note(fixes, "为未加引号的键补上双引号")
    return colon + 1


def _consume_literal(text: str, i: int, out: list[str]) -> int:
    n = len(text)
    for word, replacement in _LITERALS:
        if text.startswith(word, i):
            end = i + len(word)
            if end >= n or not (text[end].isalnum() or text[end] in "_$"):
                out.append(replacement)
                return len(word)
    return 0


# ================================================================ 输出
def dumps(
    obj: Any,
    indent: int | str | None = 2,
    sort_keys: bool = False,
    ensure_ascii: bool = False,
) -> str:
    # indent 为 None 时使用最紧凑的分隔符，避免出现 ": " / ", " 这些多余空格
    separators = None if indent is not None else (",", ":")
    return json.dumps(
        obj, indent=indent, sort_keys=sort_keys, ensure_ascii=ensure_ascii,
        separators=separators,
    )


def format_text(
    text: str,
    indent: int | str = 2,
    sort_keys: bool = False,
    ensure_ascii: bool = False,
    lenient: bool = False,
    report: list[str] | None = None,
) -> str:
    """格式化（美化）JSON 文本。"""
    obj, fixes = loads_ex(text, lenient)
    if report is not None:
        report.extend(fixes)
    return dumps(obj, indent=indent, sort_keys=sort_keys, ensure_ascii=ensure_ascii)


def minify(
    text: str,
    ensure_ascii: bool = False,
    lenient: bool = False,
    report: list[str] | None = None,
) -> str:
    """压缩为单行 JSON。"""
    obj, fixes = loads_ex(text, lenient)
    if report is not None:
        report.extend(fixes)
    return dumps(obj, indent=None, ensure_ascii=ensure_ascii)


def sort_keys_deep(text: str, ensure_ascii: bool = False,
                   lenient: bool = False, report: list[str] | None = None) -> str:
    """按键名递归排序后美化输出。"""
    return format_text(text, indent=2, sort_keys=True, ensure_ascii=ensure_ascii,
                       lenient=lenient, report=report)


def validate(
    text: str,
    lenient: bool = False,
    report: list[str] | None = None,
) -> str:
    """校验并返回摘要信息。"""
    obj, fixes = loads_ex(text, lenient)
    if report is not None:
        report.extend(fixes)
    if isinstance(obj, dict):
        summary = f"合法 JSON · 根为对象 · {len(obj)} 个顶层键"
    elif isinstance(obj, list):
        summary = f"合法 JSON · 根为数组 · {len(obj)} 个元素"
    else:
        summary = f"合法 JSON · 根为 {type(obj).__name__}"
    if fixes:
        summary += f" · 已自动修复 {len(fixes)} 类问题"
    return summary


# --------------------------------------------------------------- 转义相关
def escape_string(text: str) -> str:
    """转成 JSON 字符串字面量（含外层引号与 \\" \\n 等转义）。"""
    return json.dumps(text, ensure_ascii=False)


def unescape_string(text: str) -> str:
    """把 JSON 字符串字面量还原成原始文本。"""
    stripped = (text or "").strip()
    if not stripped:
        raise JsonError("内容为空")
    if not (stripped.startswith('"') and stripped.endswith('"') and len(stripped) >= 2):
        stripped = '"' + stripped + '"'
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise JsonError(
            "不是合法的转义字符串，请检查引号与反斜杠是否正确", stripped, exc.pos
        ) from None
    if not isinstance(value, str):
        raise JsonError("内容不是一个字符串")
    return value


def to_ascii_escape(text: str) -> str:
    """非 ASCII 字符全部转成 \\uXXXX 形式。"""
    return json.dumps(text, ensure_ascii=True)


def from_ascii_escape(text: str) -> str:
    """还原 \\uXXXX 转义。"""
    return unescape_string(text)


# --------------------------------------------------------------- 取值查询
_PATH_TOKEN = re.compile(r"([^.\[\]]+)|\[(\d+|\*)\]")


def query(obj: Any, path: str) -> Any:
    """按 `a.b[0].c` 形式的路径取值，`[*]` 表示数组展开。"""
    path = (path or "").strip()
    if not path:
        return obj
    tokens: list[Any] = []
    for name, index in _PATH_TOKEN.findall(path):
        tokens.append(name if name else (int(index) if index != "*" else "*"))

    results: list[Any] = [obj]
    for token in tokens:
        nxt: list[Any] = []
        for node in results:
            if token == "*":
                if isinstance(node, list):
                    nxt.extend(node)
                elif isinstance(node, dict):
                    nxt.extend(node.values())
            elif isinstance(token, int):
                if isinstance(node, list) and -len(node) <= token < len(node):
                    nxt.append(node[token])
            elif isinstance(node, dict) and token in node:
                nxt.append(node[token])
        results = nxt
        if not results:
            raise JsonError(f"路径 {path!r} 没有匹配到任何值")
    return results[0] if len(results) == 1 else results


def stats(text: str, lenient: bool = False) -> str:
    """返回 JSON 结构概览。"""
    obj = loads(text, lenient)
    parts: list[str] = []

    def walk(node: Any, depth: int) -> None:
        pad = "  " * depth
        if isinstance(node, dict):
            parts.append(f"{pad}对象({len(node)} 键)")
            for key, value in node.items():
                if isinstance(value, (dict, list)):
                    parts.append(f"{pad}  {key}:")
                    walk(value, depth + 2)
                else:
                    parts.append(f"{pad}  {key}: {type(value).__name__}")
        elif isinstance(node, list):
            parts.append(f"{pad}数组[{len(node)}]")
            if node:
                walk(node[0], depth + 1)
        else:
            parts.append(f"{pad}{type(node).__name__}")

    walk(obj, 0)
    if len(parts) > 200:
        parts = parts[:200] + ["... 已截断"]
    return "\n".join(parts)
