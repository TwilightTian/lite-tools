"""启动变量格式互转：IDEA 环境变量 / Linux export / .env / docker -e / JSON。

IDEA  Run Configuration 的 Environment variables 输入框格式：`A=1;B=2`
Linux shell 格式：`export A=1`（也支持同一行 `A=1;B=2`）
"""

from __future__ import annotations

import json
import re
from typing import Iterable

FORMATS = ["IDEA", "Linux export", ".env", "docker -e", "JSON"]


class EnvParseError(ValueError):
    pass


# ================================================================ 解析
def parse_idea(text: str) -> list[tuple[str, str]]:
    """解析 IDEA 环境变量串。分号分隔，值可用双引号包裹以容纳分号或空格。"""
    text = (text or "").strip()
    if not text:
        return []
    return [_split_pair(chunk) for chunk in _split_statements(text, allow_newline=True)
            if chunk.strip()]


def parse_shell(text: str) -> list[tuple[str, str]]:
    """解析 `export A=1` / `A=1`，支持同一行用 `;` 或 `&&` 连接多条。"""
    pairs: list[tuple[str, str]] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        for chunk in _split_statements(line):
            chunk = re.sub(r"^export\s+", "", chunk.strip())
            if chunk and "=" in chunk:
                pairs.append(_split_pair(chunk))
    return pairs


def parse_dotenv(text: str) -> list[tuple[str, str]]:
    """解析 .env：每行 KEY=VALUE，支持引号、注释。"""
    pairs: list[tuple[str, str]] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        pairs.append(_split_pair(line))
    return pairs


def parse_docker(text: str) -> list[tuple[str, str]]:
    """解析 `-e A=1 -e B=2`，也兼容每行一个的写法。"""
    text = (text or "").strip()
    if not text:
        return []
    if "\n" in text:
        text = " ".join(part.strip() for part in text.splitlines() if part.strip())
    pairs: list[tuple[str, str]] = []
    for match in re.finditer(r"-e(?:=|[\s])+((?:[^\s\"']|\"[^\"]*\"|'[^']*')+?)(?=\s+-e|$)", text):
        chunk = match.group(1).strip()
        if chunk:
            pairs.append(_split_pair(chunk))
    if not pairs:  # 退化：当作每行 KEY=VALUE 处理
        pairs = parse_shell(text)
    return pairs


def parse_json(text: str) -> list[tuple[str, str]]:
    """解析 {"A": "1"} 形式。"""
    try:
        data = json.loads(text or "{}")
    except ValueError as exc:
        raise EnvParseError(f"JSON 解析失败：{exc}") from exc
    if not isinstance(data, dict):
        raise EnvParseError("顶层必须是对象")
    return [(str(k), _stringify(v)) for k, v in data.items()]


def _stringify(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


PARSERS = {
    "IDEA": parse_idea,
    "Linux export": parse_shell,
    ".env": parse_dotenv,
    "docker -e": parse_docker,
    "JSON": parse_json,
}


def parse(text: str, fmt: str) -> list[tuple[str, str]]:
    parser = PARSERS.get(fmt)
    if parser is None:
        raise EnvParseError(f"不支持的格式：{fmt}")
    try:
        return parser(text)
    except EnvParseError:
        raise
    except ValueError as exc:
        raise EnvParseError(str(exc)) from exc


def _split_statements(text: str, allow_newline: bool = False) -> list[str]:
    """按分号拆分多条赋值语句，引号内部的符号不拆。

    IDEA 格式支持分号；shell 里 `A=1;B=2` 与 `A=1 && B=2` 同样常见。
    """
    parts: list[str] = []
    buf: list[str] = []
    quote = ""
    index = 0
    length = len(text)
    separators = ";\n\r" if allow_newline else ";"
    while index < length:
        char = text[index]
        if quote:
            buf.append(char)
            if char == "\\" and index + 1 < length:
                buf.append(text[index + 1])
                index += 2
                continue
            if char == quote:
                quote = ""
            index += 1
            continue
        if char in "\"'":
            quote = char
            buf.append(char)
        elif char in separators:
            parts.append("".join(buf))
            buf = []
        elif text.startswith("&&", index):
            parts.append("".join(buf))
            buf = []
            index += 2
            continue
        else:
            buf.append(char)
        index += 1
    tail = "".join(buf)
    if tail.strip():
        parts.append(tail)
    return parts


def _split_pair(chunk: str) -> tuple[str, str]:
    """拆出一对键值，并把外层引号及其内部的转义还原成真实内容。"""
    if "=" not in chunk:
        return chunk.strip(), ""
    key, _, value = chunk.partition("=")
    key = key.strip()
    value = value.strip()

    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        quote = value[0]
        value = value[1:-1]
        if quote == '"':
            value = re.sub(r'\\(["\\])', r"\1", value)
        else:
            # shell 里单引号内的引号靠拼接表示：'it'\''s' 实际是 it's
            value = value.replace("'\\''", "'")
    return key, value


# ================================================================ 生成
_SHELL_SAFE = re.compile(r"^[A-Za-z0-9_./:@%+,-]+$")
_IDEA_SAFE = re.compile(r"^[^\s;\"]*$")


def shell_quote(value: str) -> str:
    """按 shell 规则加引号。

    含 `$` 或反引号的值必须用双引号，否则变量与命令替换会被单引号屏蔽掉。
    """
    if value == "":
        return ""
    if _SHELL_SAFE.match(value):
        return value
    if "$" in value or "`" in value:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`")
        return f'"{escaped}"'
    return "'" + value.replace("'", "'\"'\"'") + "'"


def idea_quote(value: str) -> str:
    if value == "" or _IDEA_SAFE.match(value):
        return value
    return '"' + value.replace('"', '\\"') + '"'


def dotenv_quote(value: str) -> str:
    if value == "":
        return ""
    if re.search(r"[\s\"'#$]", value):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return value


def docker_quote(value: str) -> str:
    return shell_quote(value)


def to_idea(pairs: Iterable[tuple[str, str]]) -> str:
    return ";".join(f"{key}={idea_quote(value)}" for key, value in pairs)


def to_shell(pairs: Iterable[tuple[str, str]]) -> str:
    return "\n".join(f"export {key}={shell_quote(value)}" for key, value in pairs)


def to_dotenv(pairs: Iterable[tuple[str, str]]) -> str:
    return "\n".join(f"{key}={dotenv_quote(value)}" for key, value in pairs)


def to_docker(pairs: Iterable[tuple[str, str]]) -> str:
    return "\n".join(f"-e {key}={docker_quote(value)}" for key, value in pairs)


def to_json(pairs: Iterable[tuple[str, str]]) -> str:
    return json.dumps({k: v for k, v in pairs}, indent=2, ensure_ascii=False)


RENDERERS = {
    "IDEA": to_idea,
    "Linux export": to_shell,
    ".env": to_dotenv,
    "docker -e": to_docker,
    "JSON": to_json,
}


def render(pairs: Iterable[tuple[str, str]], fmt: str) -> str:
    renderer = RENDERERS.get(fmt)
    if renderer is None:
        raise EnvParseError(f"不支持的格式：{fmt}")
    return renderer(list(pairs))


def convert(text: str, source: str, target: str) -> str:
    """把 `text` 从 `source` 格式转成 `target` 格式。"""
    return render(parse(text, source), target)
