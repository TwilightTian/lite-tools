"""时间戳 / 日期字符串互转。"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any

WEEKDAYS_CN = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]

# 常用时区（名称, 相对 UTC 小时）
COMMON_ZONES: list[tuple[str, float]] = [
    ("UTC", 0.0),
    ("北京时间 UTC+8", 8.0),
    ("东京 UTC+9", 9.0),
    ("新德里 UTC+5:30", 5.5),
    ("莫斯科 UTC+3", 3.0),
    ("伦敦 UTC+0", 0.0),
    ("巴黎 UTC+1", 1.0),
    ("纽约 UTC-5", -5.0),
    ("洛杉矶 UTC-8", -8.0),
]

_DATE_PATTERNS: list[str] = [
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%Y/%m/%d",
    "%Y.%m.%d",
    "%Y年%m月%d日 %H:%M:%S",
    "%Y年%m月%d日",
    "%Y%m%d%H%M%S",
    "%Y%m%d",
    "%d/%b/%Y:%H:%M:%S",  # Nginx 日志
    "%b %d %Y %H:%M:%S",
    "%H:%M:%S",
    "%H:%M",
]


class TimeParseError(ValueError):
    pass


def _local_zone() -> timezone:
    return datetime.now().astimezone().tzinfo or timezone.utc


def resolve_zone(offset: str | float | None) -> timezone:
    """把 'local' / 'UTC' / 8 / 5.5 解析成 tzinfo。"""
    if offset is None or offset == "local":
        return _local_zone()  # type: ignore[return-value]
    if isinstance(offset, str) and offset.upper() == "UTC":
        return timezone.utc
    hours = float(offset)
    return timezone(timedelta(hours=hours))


def now_millis() -> int:
    return int(datetime.now().timestamp() * 1000)


def parse_input(text: str, zone: timezone | None = None) -> datetime:
    """解析用户输入：时间戳（秒/毫秒/微秒）、now、常见日期格式、ISO8601、RFC2822。"""
    zone = zone or _local_zone()
    result = _parse_raw((text or "").strip(), zone)
    if result.tzinfo is None:
        result = result.replace(tzinfo=zone)
    return result


def _parse_raw(raw: str, zone: timezone) -> datetime:
    if not raw:
        raise TimeParseError("请输入时间戳或日期时间字符串")

    lowered = raw.lower()
    if lowered in {"now", "当前", "现在"}:
        return datetime.now(zone)

    # 纯数字 -> 时间戳或紧凑日期（YYYYMMDD / YYYYMMDDHHMMSS）
    if re.fullmatch(r"[+-]?\d+", raw):
        digits = raw.lstrip("+-")
        value = int(raw)
        compact = _guess_compact_date(digits)
        if compact is not None:
            return compact.replace(tzinfo=zone)
        if len(digits) <= 10:
            return datetime.fromtimestamp(value, tz=zone)
        if len(digits) <= 13:
            return datetime.fromtimestamp(value / 1000.0, tz=zone)
        if len(digits) <= 16:
            return datetime.fromtimestamp(value / 1_000_000.0, tz=zone)
        return datetime.fromtimestamp(value / 1_000_000_000.0, tz=zone)

    # 纯小数 -> 秒级带毫秒
    if re.fullmatch(r"\d+\.\d+", raw):
        return datetime.fromtimestamp(float(raw), tz=zone)

    # 去掉时区后缀 Z / 毫秒截断
    candidate = raw
    try:
        return datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError:
        pass

    # ISO 带空格分隔
    try:
        return datetime.strptime(candidate, "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        pass

    # RFC2822 / HTTP 日期
    if "," in candidate and any(m in candidate for m in ("GMT", "+", "-")):
        try:
            return parsedate_to_datetime(candidate)
        except (TypeError, ValueError):
            pass

    for pattern in _DATE_PATTERNS:
        try:
            parsed = datetime.strptime(candidate, pattern)
        except ValueError:
            continue
        if pattern in {"%H:%M:%S", "%H:%M"}:
            today = datetime.now(zone)
            parsed = parsed.replace(year=today.year, month=today.month, day=today.day)
        return parsed.replace(tzinfo=zone)

    raise TimeParseError(f"无法识别的格式：{raw}")


def _guess_compact_date(digits: str) -> datetime | None:
    """识别 YYYYMMDD / YYYYMMDDHHMMSS 形式的紧凑日期。

    8 位纯数字既可能是时间戳也可能是日期，这里对明显像年份的前缀做日期优先处理。
    """
    if len(digits) not in (8, 14):
        return None
    year = int(digits[0:4])
    if not 1900 <= year <= 2999:
        return None
    month, day = int(digits[4:6]), int(digits[6:8])
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    hour = minute = second = 0
    if len(digits) == 14:
        hour, minute, second = int(digits[8:10]), int(digits[10:12]), int(digits[12:14])
        if hour > 23 or minute > 59 or second > 59:
            return None
    try:
        return datetime(year, month, day, hour, minute, second)
    except ValueError:
        return None


def humanize(dt: datetime, now: datetime | None = None) -> str:
    """相对当前时间的描述。"""
    now = now or datetime.now(dt.tzinfo or _local_zone())
    delta = (now - dt).total_seconds()
    future = delta < 0
    delta = abs(delta)
    if delta < 5:
        return "刚刚"
    if delta < 60:
        value, unit = delta, "秒"
    elif delta < 3600:
        value, unit = delta / 60, "分钟"
    elif delta < 86400:
        value, unit = delta / 3600, "小时"
    elif delta < 86400 * 30:
        value, unit = delta / 86400, "天"
    elif delta < 86400 * 365:
        value, unit = delta / (86400 * 30), "个月"
    else:
        value, unit = delta / (86400 * 365), "年"
    text = f"{value:.1f}{unit}".replace(".0", "")
    return f"{text}后" if future else f"{text}前"


def describe(text: str, zone: timezone | None = None) -> list[tuple[str, str]]:
    """把输入解析后展开成一组「名称 -> 值」，用于界面展示与复制。"""
    dt = parse_input(text, zone)
    utc_dt = dt.astimezone(timezone.utc)
    local_dt = dt.astimezone(_local_zone())
    iso = dt.isoformat(timespec="seconds" if dt.microsecond == 0 else "milliseconds")

    items: list[tuple[str, str]] = [
        ("Unix 秒", str(int(dt.timestamp()))),
        ("Unix 毫秒", str(int(dt.timestamp() * 1000))),
        ("Unix 微秒", str(int(dt.timestamp() * 1_000_000))),
        ("本地时间", local_dt.strftime("%Y-%m-%d %H:%M:%S")),
        ("本地时间(毫秒)", local_dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]),
        ("UTC 时间", utc_dt.strftime("%Y-%m-%d %H:%M:%S")),
        ("ISO8601", iso),
        ("RFC1123", dt.strftime("%a, %d %b %Y %H:%M:%S %z")),
        ("中文格式", dt.strftime("%Y年%m月%d日 %H:%M:%S")),
        ("日期", dt.strftime("%Y-%m-%d")),
        ("时间", dt.strftime("%H:%M:%S")),
        ("星期", WEEKDAYS_CN[dt.weekday()]),
        ("年内第几天", str(dt.timetuple().tm_yday)),
        ("年内第几周", str(dt.isocalendar()[1])),
        ("Java 格式", dt.strftime("%a %b %d %H:%M:%S %Z %Y")),
        ("相对时间", humanize(dt)),
    ]
    return items


def convert_to_zones(text: str, zone: timezone | None = None) -> list[tuple[str, str]]:
    """把输入换算到若干常用时区。"""
    dt = parse_input(text, zone)
    out: list[tuple[str, str]] = []
    for name, hours in COMMON_ZONES:
        zoned = dt.astimezone(timezone(timedelta(hours=hours)))
        out.append((name, zoned.strftime("%Y-%m-%d %H:%M:%S")))
    return out


def batch_convert(text: str, zone: timezone | None = None) -> list[tuple[str, str, str]]:
    """批量转换：每行一个输入，返回 (原文, 本地时间, 时间戳秒)。"""
    rows: list[tuple[str, str, str]] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            dt = parse_input(line, zone)
        except TimeParseError as exc:
            rows.append((line, f"错误：{exc}", ""))
            continue
        rows.append(
            (
                line,
                dt.astimezone(_local_zone()).strftime("%Y-%m-%d %H:%M:%S"),
                str(int(dt.timestamp())),
            )
        )
    return rows


def fmt(dt: datetime, pattern: str) -> str:
    return dt.strftime(pattern)


def to_java_date(text: str) -> dict[str, Any]:
    """给 Java 开发者常用的几种写法。"""
    dt = parse_input(text)
    millis = int(dt.timestamp() * 1000)
    return {
        "new Date(": f"new Date({millis}L)",
        "System.currentTimeMillis()": f"{millis}L",
        "LocalDateTime": dt.strftime("%Y-%m-%dT%H:%M:%S"),
        "SimpleDateFormat": f'new SimpleDateFormat("yyyy-MM-dd HH:mm:ss").parse("{dt.strftime("%Y-%m-%d %H:%M:%S")}")',
    }
