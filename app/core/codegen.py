"""Java 实体类 <-> JSON 双向转换。

java_to_json : 解析 Java 源码中的字段（支持泛型、集合、嵌套类），生成示例 JSON。
json_to_java : 由 JSON 样本反向生成 Java POJO（可带 Lombok / Jackson 注解）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

MODIFIERS = {
    "public",
    "private",
    "protected",
    "static",
    "final",
    "transient",
    "volatile",
    "synchronized",
    "abstract",
    "native",
    "strictfp",
    "default",
}

# 出现在声明里就说明它不是字段（类头、控制流、方法调用等）
NON_FIELD_KEYWORDS = {
    "class", "interface", "enum", "record", "extends", "implements", "package",
    "import", "return", "new", "throw", "throws", "if", "else", "for", "while",
    "do", "switch", "case", "break", "continue", "try", "catch", "finally",
    "instanceof", "assert", "super", "this", "void", "yield",
}

NUMBER_TYPES = {
    "byte",
    "short",
    "int",
    "long",
    "float",
    "double",
    "Byte",
    "Short",
    "Integer",
    "Long",
    "Float",
    "Double",
    "BigInteger",
    "BigDecimal",
    "Number",
}

DATE_TYPES = {
    "Date",
    "LocalDate",
    "LocalDateTime",
    "LocalTime",
    "Instant",
    "Timestamp",
    "OffsetDateTime",
    "ZonedDateTime",
    "java.sql.Date",
    "java.sql.Timestamp",
}

STRING_TYPES = {"String", "CharSequence", "Character", "char", "StringBuilder"}

BOOL_TYPES = {"boolean", "Boolean"}

ARRAY_TYPES = {"List", "ArrayList", "LinkedList", "Set", "HashSet", "TreeSet",
               "Collection", "Iterable", "Queue", "Deque", "Vector"}

MAP_TYPES = {"Map", "HashMap", "TreeMap", "LinkedHashMap", "ConcurrentHashMap",
             "Properties", "Hashtable"}


class CodegenError(ValueError):
    pass


# ============================================================ Java -> JSON
@dataclass
class JavaField:
    name: str
    type: str


@dataclass
class JavaClass:
    name: str
    fields: list[JavaField] = field(default_factory=list)


def java_to_json(source: str, root: str | None = None, depth: int = 3,
                 date_sample: str | None = None) -> str:
    """解析 Java 源码并生成示例 JSON 文本。"""
    import json

    classes = _parse_classes(source)
    if not classes:
        raise CodegenError("没有解析到任何 class / interface / enum 定义")

    if not root:
        root = next(iter(classes))
    elif root not in classes:
        raise CodegenError(f"未找到类 {root}，可选：{', '.join(classes)}")

    stamp = date_sample or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data = _build_object(classes[root], classes, depth, set(), stamp)
    return json.dumps(data, indent=2, ensure_ascii=False)


def list_classes(source: str) -> list[str]:
    return list(_parse_classes(source).keys())


def _parse_classes(source: str) -> dict[str, JavaClass]:
    source = _strip_comments(source)
    result: dict[str, JavaClass] = {}
    for match in re.finditer(r"\b(?:class|interface|enum)\s+([A-Za-z_$][\w$]*)", source):
        name = match.group(1)
        brace = source.find("{", match.end())
        if brace < 0:
            continue
        end = _match_brace(source, brace)
        body = source[brace + 1:end]
        result[name] = JavaClass(name=name, fields=_parse_fields(body))
    return result


def _parse_fields(body: str) -> list[JavaField]:
    decls = _declarations(body)
    fields: list[JavaField] = []
    seen: set[str] = set()
    for decl in decls:
        parsed = _parse_decl(decl)
        if parsed and parsed.name not in seen:
            seen.add(parsed.name)
            fields.append(parsed)
    return fields


def _declarations(body: str) -> list[str]:
    """切分出字段声明语句（丢弃方法体、内部类体、初始化块）。"""
    cleaned = _remove_code_blocks(body)
    statements: list[str] = []
    buf: list[str] = []
    depth = 0
    i = 0
    n = len(cleaned)
    while i < n:
        ch = cleaned[i]
        if ch in "\"'":
            j = _skip_literal(cleaned, i)
            buf.append(cleaned[i:j])
            i = j
            continue
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        elif ch == "<":
            depth += 1
        elif ch == ">":
            depth = max(0, depth - 1)
        if ch == ";" and depth == 0:
            statements.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
        i += 1
    if "".join(buf).strip():
        statements.append("".join(buf))
    return [s for s in (s.strip() for s in statements) if s]


def _remove_code_blocks(body: str) -> str:
    """丢弃所有花括号块（方法体、初始化块、内部类体）。

    内部类会由 `_parse_classes` 的全量扫描单独解析，这里必须排除，
    否则内部类的字段会被误算到外层类上。
    """
    out: list[str] = []
    i = 0
    n = len(body)
    while i < n:
        ch = body[i]
        if ch in "\"'":
            j = _skip_literal(body, i)
            out.append(body[i:j])
            i = j
            continue
        if ch == "{":
            i = _match_brace(body, i) + 1
            out.append(";")
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _parse_decl(decl: str) -> JavaField | None:
    text = _strip_comments(decl)
    text = re.sub(r"@[\w.]+(?:\s*\([^()]*(?:\([^()]*\)[^()]*)*\))?", " ", text)  # 去注解
    if "=" in text:
        text = text.split("=", 1)[0]
    tokens = text.replace("\n", " ").split()
    while tokens and (tokens[0] in MODIFIERS or tokens[0].startswith("@")):
        tokens.pop(0)
    if tokens and tokens[0] in NON_FIELD_KEYWORDS:
        return None
    if len(tokens) < 2:
        return None
    name = tokens.pop()
    if name.endswith("[]"):  # `String tags[]` 写法
        name = name[:-2].strip()
        tokens.append("[]")
    if not re.fullmatch(r"[A-Za-z_$][\w$]*", name) or name in NON_FIELD_KEYWORDS:
        return None
    if any(token in NON_FIELD_KEYWORDS for token in tokens):
        return None
    type_text = " ".join(tokens).strip()
    if not type_text or type_text in MODIFIERS:
        return None
    if "(" in type_text or ")" in type_text:
        return None
    return JavaField(name=name, type=_normalize_type(type_text))


def _normalize_type(type_text: str) -> str:
    text = re.sub(r"\s+", " ", type_text).strip()
    text = re.sub(r"\s*<\s*", "<", text)
    text = re.sub(r"\s*>\s*", ">", text)
    text = re.sub(r"\s*,\s*", ",", text)
    text = re.sub(r"\s*\[\s*\]\s*", "[]", text)
    return text


def _base_type(type_text: str) -> str:
    """去掉泛型与数组，取裸类名。"""
    text = type_text
    while text.endswith("[]"):
        text = text[:-2]
    generic = text.find("<")
    if generic > 0:
        text = text[:generic]
    return text.split(".")[-1]


def _generic_args(type_text: str) -> str:
    start = type_text.find("<")
    if start < 0:
        return ""
    return type_text[start + 1:type_text.rfind(">")]


def _split_generic_args(args: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    buf: list[str] = []
    for ch in args:
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    if "".join(buf).strip():
        parts.append("".join(buf).strip())
    return parts


def _build_value(type_text: str, classes: dict[str, JavaClass], depth: int,
                 visited: set[str], stamp: str) -> Any:
    raw = type_text.strip()
    if raw.endswith("[]"):
        if depth <= 0:
            return []
        inner = _build_value(raw[:-2], classes, depth - 1, visited, stamp)
        return [inner]
    base = _base_type(raw)
    generics = _split_generic_args(_generic_args(raw))

    if base in STRING_TYPES:
        return ""
    if base in BOOL_TYPES:
        return True
    if base in {"long", "Long", "BigInteger"}:
        return 0
    if base in NUMBER_TYPES:
        return 0.0 if base in {"float", "double", "Float", "Double", "BigDecimal"} else 0
    if base in DATE_TYPES:
        return stamp
    if base in MAP_TYPES:
        if depth <= 0:
            return {}
        value_type = generics[1] if len(generics) > 1 else "Object"
        sample = _build_value(value_type, classes, depth - 1, visited, stamp)
        return {} if sample is None else {"key": sample}
    if base in ARRAY_TYPES:
        if depth <= 0:
            return []
        element = generics[0] if generics else "Object"
        return [_build_value(element, classes, depth - 1, visited, stamp)]
    if base in classes:
        if depth <= 0 or base in visited:
            return {}
        return _build_object(classes[base], classes, depth, visited | {base}, stamp)
    if base in {"Object", "T", "E", "K", "V", "?"}:
        return None
    return None


def _build_object(cls: JavaClass, classes: dict[str, JavaClass], depth: int,
                  visited: set[str], stamp: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for f in cls.fields:
        data[f.name] = _build_value(f.type, classes, depth, visited, stamp)
    return data


# ============================================================ JSON -> Java
@dataclass
class TypeSpec:
    kind: str                       # string/int/long/double/decimal/bool/date/object/list/any
    class_name: str | None = None
    element: "TypeSpec | None" = None


@dataclass
class FieldSpec:
    name: str                       # Java 字段名（驼峰）
    key: str                        # 原始 JSON key
    type: TypeSpec


def json_to_java(
    text: str,
    class_name: str = "Root",
    package: str = "",
    use_lombok: bool = True,
    use_jackson: bool = True,
    boxed: bool = True,
    date_as_string: bool = True,
) -> str:
    import json

    try:
        data = json.loads(text)
    except ValueError as exc:
        raise CodegenError(f"JSON 解析失败：{exc}") from exc

    if isinstance(data, list):
        if not data:
            raise CodegenError("JSON 数组为空，无法推断元素类型")
        data = data[0]
    if not isinstance(data, dict):
        raise CodegenError("顶层需要是对象，或对象构成的数组")

    class_name = _to_pascal(class_name or "Root")
    registry: dict[str, list[FieldSpec]] = {}
    _infer(data, class_name, registry, date_as_string)

    header: list[str] = []
    if package.strip():
        header.append(f"package {package.strip()};")
        header.append("")
    if use_lombok:
        header.append("import lombok.Data;")
    if use_jackson:
        header.append("import com.fasterxml.jackson.annotation.JsonProperty;")
    for imp in _collect_imports(registry):
        header.append(f"import {imp};")

    body = _render(registry, class_name, use_lombok, use_jackson, boxed)
    return "\n".join(header) + "\n\n" + body + "\n"


def _collect_imports(registry: dict[str, list[FieldSpec]]) -> list[str]:
    kinds = {field.type.kind for fields in registry.values() for field in fields}
    imports: list[str] = []
    if "list" in kinds:
        imports.append("java.util.List")
    if "decimal" in kinds:
        imports.append("java.math.BigDecimal")
    if "date" in kinds:
        imports.append("java.util.Date")
    return imports


def _infer(node: Any, hint_name: str, registry: dict[str, list[FieldSpec]],
           date_as_string: bool) -> TypeSpec:
    if isinstance(node, bool):
        return TypeSpec("bool")
    if isinstance(node, int):
        return TypeSpec("int" if -(2**31) <= node < 2**31 else "long")
    if isinstance(node, float):
        return TypeSpec("decimal")
    if isinstance(node, str):
        if not date_as_string and _looks_like_datetime(node):
            return TypeSpec("date")
        return TypeSpec("string")
    if node is None:
        return TypeSpec("any")
    if isinstance(node, list):
        if not node:
            return TypeSpec("list", element=TypeSpec("any"))
        element = _infer(node[0], _singular(hint_name), registry, date_as_string)
        for item in node[1:]:
            element = _merge(element, _infer(item, _singular(hint_name), registry, date_as_string))
        return TypeSpec("list", element=element)
    if isinstance(node, dict):
        if not node:
            return TypeSpec("object", class_name=None)
        cls_name = _unique_name(_to_pascal(hint_name or "Item"), registry)
        fields: list[FieldSpec] = []
        registry[cls_name] = fields
        for key, value in node.items():
            fields.append(
                FieldSpec(
                    name=_to_camel(key),
                    key=str(key),
                    type=_infer(value, key, registry, date_as_string),
                )
            )
        return TypeSpec("object", class_name=cls_name)
    return TypeSpec("any")


def _merge(a: TypeSpec, b: TypeSpec) -> TypeSpec:
    if a.kind == b.kind:
        if a.kind == "list" and a.element and b.element:
            return TypeSpec("list", element=_merge(a.element, b.element))
        if a.kind == "object":
            return a if a.class_name == b.class_name else TypeSpec("object", class_name=a.class_name or b.class_name)
        if a.kind == "int" and b.kind == "long":
            return TypeSpec("long")
        return a
    order = {"any": 0, "int": 1, "long": 2, "double": 3, "decimal": 4, "bool": 5,
             "string": 10, "date": 11, "list": 20, "object": 21}
    if "any" in (a.kind, b.kind):
        return b if a.kind == "any" else a
    if {a.kind, b.kind} == {"int", "long"}:
        return TypeSpec("long")
    if {a.kind, b.kind} <= {"int", "double"}:
        return TypeSpec("double")
    return a if order.get(a.kind, 0) >= order.get(b.kind, 0) else b


def _render(registry: dict[str, list[FieldSpec]], root_name: str,
            use_lombok: bool, use_jackson: bool, boxed: bool) -> str:
    """渲染根类与嵌套静态内部类。"""
    order = [root_name] + [name for name in registry if name != root_name]
    blocks: list[str] = []
    for index, name in enumerate(order):
        fields = registry.get(name)
        if fields is None:
            continue
        pad = "" if index == 0 else "    "
        lines: list[str] = []
        if use_lombok:
            lines.append(f"{pad}@Data")
        if index == 0:
            lines.append(f"public class {name} {{")
        else:
            lines.append(f"{pad}public static class {name} {{")
        for field in fields:
            if use_jackson and field.name != field.key:
                lines.append(f'{pad}    @JsonProperty("{field.key}")')
            lines.append(f"{pad}    private {_java_type(field.type, boxed)} {field.name};")
        lines.append(f"{pad}}}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _java_type(spec: TypeSpec, boxed: bool) -> str:
    table_primitive = {
        "int": "int", "long": "long", "double": "double", "bool": "boolean",
    }
    table_boxed = {
        "int": "Integer", "long": "Long", "double": "Double", "bool": "Boolean",
    }
    table = table_boxed if boxed else table_primitive
    kind = spec.kind
    if kind == "list":
        element = _java_type(spec.element or TypeSpec("any"), True)
        return f"List<{element}>"
    if kind == "object":
        return spec.class_name or "Object"
    if kind == "any":
        return "Object"
    if kind == "decimal":
        return "BigDecimal"
    if kind == "date":
        return "Date"
    return table.get(kind, "String")


# ------------------------------------------------------------------ 工具
def _strip_comments(text: str) -> str:
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in "\"'":
            j = _skip_literal(text, i)
            out.append(text[i:j])
            i = j
            continue
        if text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        if text.startswith("/*", i):
            j = text.find("*/", i)
            i = n if j < 0 else j + 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _skip_literal(text: str, start: int) -> int:
    quote = text[start]
    i = start + 1
    n = len(text)
    while i < n:
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == quote:
            return i + 1
        i += 1
    return n


def _match_brace(text: str, start: int) -> int:
    depth = 0
    i = start
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in "\"'":
            i = _skip_literal(text, i)
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return n - 1


def _to_pascal(text: str) -> str:
    parts = re.split(r"[^0-9A-Za-z]+", text or "")
    name = "".join(p[:1].upper() + p[1:] for p in parts if p)
    if not name:
        name = "Item"
    if name[0].isdigit():
        name = "C" + name
    return name


def _singular(text: str) -> str:
    lower = text.lower()
    if lower.endswith("ies") and len(text) > 3:
        return text[:-3] + "y"
    if lower.endswith("ses") and len(text) > 3:
        return text[:-2]
    if lower.endswith("s") and not lower.endswith("ss") and len(text) > 1:
        return text[:-1]
    return text


def _to_camel(key: str) -> str:
    parts = re.split(r"[^0-9A-Za-z]+", str(key))
    cleaned = [p for p in parts if p]
    if not cleaned:
        return "_field"
    head = cleaned[0]
    name = head[:1].lower() + head[1:] + "".join(p[:1].upper() + p[1:] for p in cleaned[1:])
    name = re.sub(r"[^0-9A-Za-z_$]", "_", name)
    if name[0].isdigit():
        name = "_" + name
    return name


def _unique_name(base: str, registry: dict[str, list[FieldSpec]]) -> str:
    if base not in registry:
        return base
    index = 2
    while f"{base}{index}" in registry:
        index += 1
    return f"{base}{index}"


_DATE_PATTERNS = [
    re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}"),
    re.compile(r"^\d{4}-\d{2}-\d{2}$"),
    re.compile(r"^\d{2}:\d{2}:\d{2}$"),
]


def _looks_like_datetime(text: str) -> bool:
    return any(p.match(text) for p in _DATE_PATTERNS)
