"""生成应用图标（纯 Python 绘制 ICO，不依赖任何图形库）。"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

from ..config import CONFIG_DIR

ICON_NAME = "litetools.ico"

# 圆角矩形背景 + 白色闪电
_BG = (47, 111, 237)
_FG = (255, 255, 255)
_LIGHTNING = [
    (17.5, 3.0),
    (8.0, 18.5),
    (14.5, 18.5),
    (12.0, 29.0),
    (23.5, 13.5),
    (16.5, 13.5),
]
_GRID = 32.0


def _in_round_rect(x: float, y: float, size: float, radius: float) -> bool:
    cx = min(max(x, radius), size - radius)
    cy = min(max(y, radius), size - radius)
    dx, dy = x - cx, y - cy
    return dx * dx + dy * dy <= radius * radius


def _in_polygon(x: float, y: float, points: list[tuple[float, float]]) -> bool:
    inside = False
    count = len(points)
    for i in range(count):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % count]
        if (y1 > y) != (y2 > y):
            slope = (x2 - x1) / (y2 - y1) if y2 != y1 else 0.0
            if x < x1 + (y - y1) * slope:
                inside = not inside
    return inside


def _render_rgba(size: int, supersample: int = 2) -> bytes:
    """渲染 size x size 的 RGBA 位图（含超采样抗锯齿）。"""
    scale = size * supersample
    radius = scale * 0.22
    poly = [(px / _GRID * scale, py / _GRID * scale) for px, py in _LIGHTNING]
    pixels = bytearray(size * size * 4)

    for py in range(size):
        for px in range(size):
            alpha_sum = 0
            bg_sum = [0, 0, 0]
            fg_sum = [0, 0, 0]
            for sy in range(supersample):
                for sx in range(supersample):
                    sample_x = px * supersample + sx + 0.5
                    sample_y = py * supersample + sy + 0.5
                    if not _in_round_rect(sample_x, sample_y, scale, radius):
                        continue
                    alpha_sum += 1
                    if _in_polygon(sample_x, sample_y, poly):
                        for i in range(3):
                            fg_sum[i] += _FG[i]
                    else:
                        for i in range(3):
                            fg_sum[i] += _BG[i]
            total = supersample * supersample
            offset = (py * size + px) * 4
            if alpha_sum == 0:
                continue
            pixels[offset + 3] = int(255 * alpha_sum / total)
            for i in range(3):
                pixels[offset + i] = int(fg_sum[i] / alpha_sum)
    return bytes(pixels)


def build_ico(sizes: tuple[int, ...] = (16, 32, 48)) -> bytes:
    """只生成 Windows 实际会用到的小尺寸，减少首次启动的绘制开销。"""
    images: list[tuple[int, bytes]] = [(s, _render_rgba(s)) for s in sizes]

    header = struct.pack("<HHH", 0, 1, len(images))
    offset = len(header) + 16 * len(images)
    entries = bytearray()
    payload = bytearray()
    for size, rgba in images:
        mask_row = ((size + 31) // 32) * 4
        mask = bytes(mask_row * size)
        bitmap_header = struct.pack(
            "<IiiHHIIiiII",
            40, size, size * 2, 1, 32, 0, len(rgba) + len(mask), 0, 0, 0, 0,
        )
        # ICO 里的像素行自下而上
        rows = [rgba[y * size * 4:(y + 1) * size * 4] for y in range(size)]
        flipped = b"".join(reversed(rows))
        blob = bitmap_header + flipped + mask
        entries += struct.pack(
            "<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(blob), offset
        )
        offset += len(blob)
        payload += blob
    return bytes(header + entries + payload)


def ensure_icon() -> Path | None:
    """确保图标文件存在，返回路径；失败返回 None。"""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        path = CONFIG_DIR / ICON_NAME
        if not path.exists() or path.stat().st_size < 100:
            path.write_bytes(build_ico())
        return path
    except OSError:
        return None


def apply_to_window(root) -> None:
    """给窗口设置图标。"""
    if sys.platform == "win32":
        path = ensure_icon()
        if path is not None:
            try:
                root.iconbitmap(default=str(path))
                return
            except Exception:  # noqa: BLE001
                pass
    try:
        from tkinter import PhotoImage

        icon = PhotoImage(width=32, height=32)
        root.iconphoto(True, icon)
    except Exception:  # noqa: BLE001
        pass
