"""网络小工具：本机 IP / 公网 IP / DNS 解析 / ping / DNS 缓存清理 / 端口连通性。"""

from __future__ import annotations

import ipaddress
import re
import socket
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable, Iterator
from urllib.request import Request, urlopen

IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

DEFAULT_TIMEOUT = 3.0


class NetError(RuntimeError):
    pass


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8", "gbk", "latin-1"):
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def _run(args: list[str], timeout: float = 20.0) -> str:
    try:
        proc = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0,
        )
    except FileNotFoundError as exc:
        raise NetError(f"命令不存在：{args[0]}") from exc
    except subprocess.TimeoutExpired:
        raise NetError("命令执行超时") from None
    return _decode(proc.stdout or b"")


# ------------------------------------------------------------------ 本机 IP
@dataclass
class Address:
    interface: str
    ip: str
    netmask: str = ""
    gateway: str = ""
    kind: str = "IPv4"


def primary_ip() -> str:
    """获取本机默认出口 IPv4。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"
    finally:
        sock.close()


def hostname() -> str:
    try:
        return socket.gethostname()
    except OSError:
        return "unknown"


def local_addresses() -> list[Address]:
    """列出所有网卡的 IPv4 地址。"""
    if IS_WINDOWS:
        return _windows_addresses()
    return _unix_addresses()


def _windows_addresses() -> list[Address]:
    text = _run(["ipconfig"], timeout=10)
    results: list[Address] = []
    current = ""
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        if not line.startswith(" ") and line.endswith(":"):
            current = line.rstrip(":").strip()
            continue
        match = re.search(r"IPv4[^:]*:\s*([0-9.]+)", line)
        if match:
            results.append(Address(interface=current or "未知适配器", ip=match.group(1)))
            continue
        mask = re.search(r"(?:子网掩码|Subnet Mask)[^:]*:\s*([0-9.]+)", line)
        if mask and results:
            results[-1].netmask = mask.group(1)
            continue
        gateway = re.search(r"(?:默认网关|Default Gateway)[^:]*:\s*([0-9.]+)", line)
        if gateway and results:
            results[-1].gateway = gateway.group(1)
    if not results:
        try:
            results.append(Address(interface="默认", ip=primary_ip()))
        except OSError:
            pass
    return results


def _unix_addresses() -> list[Address]:
    results: list[Address] = []
    try:
        text = _run(["ip", "-o", "-4", "addr", "show"], timeout=10)
        for line in text.splitlines():
            match = re.match(r"\d+:\s+(\S+)\s+inet\s+([0-9.]+)/(\d+)", line)
            if match:
                results.append(
                    Address(interface=match.group(1), ip=match.group(2),
                            netmask=str(ipaddress.ip_network(f"0.0.0.0/{match.group(3)}").netmask))
                )
    except NetError:
        pass
    if not results:
        try:
            text = _run(["ifconfig", "-a"], timeout=10)
        except NetError:
            text = ""
        current = ""
        for line in text.splitlines():
            header = re.match(r"^(\S+?):?\s", line)
            if header and not line.startswith((" ", "\t")):
                current = header.group(1)
            match = re.search(r"inet\s+(?:addr:)?([0-9.]+)", line)
            if match and not match.group(1).startswith("127."):
                results.append(Address(interface=current, ip=match.group(1)))
    if not results:
        results.append(Address(interface="默认", ip=primary_ip()))
    return results


# ------------------------------------------------------------- 公网 IP
def public_ip(api: str = "https://api.ipify.org", timeout: float = DEFAULT_TIMEOUT) -> str:
    request = Request(api, headers={"User-Agent": "LiteTools/1.0"})
    try:
        with urlopen(request, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace").strip()
    except Exception as exc:  # noqa: BLE001 - 网络异常种类繁多
        raise NetError(f"获取公网 IP 失败：{exc}") from exc


def ip_info(ip: str, timeout: float = DEFAULT_TIMEOUT) -> str:
    """通过公共接口查询 IP 归属地。"""
    request = Request(
        f"http://ip-api.com/json/{ip}?lang=zh-CN&fields=status,country,regionName,city,isp,org,as,query,message",
        headers={"User-Agent": "LiteTools/1.0"},
    )
    try:
        with urlopen(request, timeout=timeout) as resp:
            import json

            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as exc:  # noqa: BLE001
        raise NetError(f"查询失败：{exc}") from exc
    if data.get("status") != "success":
        raise NetError(data.get("message") or "查询失败")
    parts = [
        f"IP：{data.get('query', ip)}",
        f"国家/地区：{data.get('country', '-')}",
        f"区域：{data.get('regionName', '-')}",
        f"城市：{data.get('city', '-')}",
        f"运营商：{data.get('isp', '-')}",
        f"组织：{data.get('org', '-')}",
        f"ASN：{data.get('as', '-')}",
    ]
    return "\n".join(parts)


# ------------------------------------------------------------- DNS
def resolve(host: str) -> list[tuple[str, str]]:
    """解析域名，返回 (类型, 地址)。"""
    host = host.strip()
    if not host:
        raise NetError("请输入域名")
    results: list[tuple[str, str]] = []
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise NetError(f"解析失败：{exc}") from exc
    seen: set[str] = set()
    for family, _, _, _, sockaddr in infos:
        address = sockaddr[0]
        if address in seen:
            continue
        seen.add(address)
        kind = "IPv4" if family == socket.AF_INET else "IPv6"
        results.append((kind, address))
    return results


def flush_dns() -> str:
    """清理系统 DNS 缓存。"""
    if IS_WINDOWS:
        return _run(["ipconfig", "/flushdns"], timeout=20).strip() or "已执行 ipconfig /flushdns"
    if IS_MAC:
        output = _run(["dscacheutil", "-flushcache"], timeout=20)
        output += _run(["killall", "-HUP", "mDNSResponder"], timeout=20)
        return output.strip() or "已刷新 macOS DNS 缓存"
    errors: list[str] = []
    for args in (
        ["resolvectl", "flush-caches"],
        ["systemd-resolve", "--flush-caches"],
        ["service", "nscd", "restart"],
    ):
        try:
            return _run(args, timeout=20).strip() or f"已执行 {' '.join(args)}"
        except NetError as exc:
            errors.append(f"{' '.join(args)} -> {exc}")
    raise NetError("未找到可用的 DNS 刷新命令，可尝试：\n" + "\n".join(errors))


# ------------------------------------------------------------- ping
def ping_command(host: str, count: int = 4, timeout: float = DEFAULT_TIMEOUT) -> list[str]:
    if IS_WINDOWS:
        return ["ping", "-n", str(count), "-w", str(int(timeout * 1000)), host]
    if IS_MAC:
        return ["ping", "-c", str(count), "-W", str(int(timeout * 1000)), host]
    return ["ping", "-c", str(count), "-W", str(int(timeout)), host]


def ping(host: str, count: int = 4, timeout: float = DEFAULT_TIMEOUT) -> Iterator[str]:
    """逐行产出 ping 输出。"""
    host = (host or "").strip()
    if not host:
        raise NetError("请输入主机或域名")
    args = ping_command(host, count, timeout)
    try:
        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0,
        )
    except FileNotFoundError as exc:
        raise NetError(f"系统没有 ping 命令：{exc}") from exc
    assert proc.stdout is not None
    for raw in proc.stdout:
        yield _decode(raw).rstrip("\r\n")
    proc.wait()


def parse_ping_summary(lines: list[str]) -> str:
    """从 ping 输出中提取丢包率与平均延迟（中英文兼容）。"""
    text = "\n".join(lines)
    loss = re.search(r"(\d+(?:\.\d+)?)%\s*(?:loss|丢失)", text)
    times = [float(m) for m in re.findall(r"[=<]\s*(\d+(?:\.\d+)?)\s*ms", text)]
    parts: list[str] = []
    if loss:
        parts.append(f"丢包 {loss.group(1)}%")
    if times:
        parts.append(f"平均 {sum(times) / len(times):.1f} ms")
        parts.append(f"最小 {min(times):.0f} ms")
        parts.append(f"最大 {max(times):.0f} ms")
    return " · ".join(parts)


# ------------------------------------------------------------- 端口连通（telnet）
def tcp_check(host: str, port: int, timeout: float = DEFAULT_TIMEOUT) -> tuple[bool, str]:
    host = (host or "").strip()
    try:
        addresses = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        return False, f"域名解析失败：{exc}"
    if not addresses:
        return False, "没有可用的地址"
    last_error = ""
    import time

    for family, socktype, proto, _, sockaddr in addresses:
        started = time.perf_counter()
        sock = socket.socket(family, socktype, proto)
        sock.settimeout(timeout)
        try:
            sock.connect(sockaddr)
        except OSError as exc:
            last_error = str(exc)
            sock.close()
            continue
        elapsed = (time.perf_counter() - started) * 1000
        try:
            sock.close()
        except OSError:
            pass
        return True, f"端口开放，连接耗时 {elapsed:.0f} ms"
    return False, f"端口不通：{last_error or '连接被拒绝'}"


def check_ports(host: str, ports: list[int], timeout: float = DEFAULT_TIMEOUT,
                on_result: Callable[[int, bool, str], None] | None = None) -> list[tuple[int, bool, str]]:
    results: list[tuple[int, bool, str]] = []
    for port in ports:
        ok, message = tcp_check(host, port, timeout)
        results.append((port, ok, message))
        if on_result:
            on_result(port, ok, message)
    return results


def parse_ports(text: str) -> list[int]:
    """解析 `80,443,8000-8010` 形式的端口列表。"""
    ports: list[int] = []
    for chunk in re.split(r"[,，\s]+", text or ""):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            start_text, _, end_text = chunk.partition("-")
            try:
                start, end = int(start_text), int(end_text)
            except ValueError:
                continue
            if start > end:
                start, end = end, start
            ports.extend(range(max(1, start), min(65535, end) + 1))
        else:
            try:
                ports.append(int(chunk))
            except ValueError:
                continue
    return sorted({p for p in ports if 0 < p <= 65535})
