"""平台相关能力：开机自启 / 全局热键 / 托盘 / 应用图标。

所有实现都对平台做能力探测，不可用时返回明确的原因而不是抛异常。
"""

from . import autostart, hotkey, icon

try:
    from . import tray
except Exception:  # noqa: BLE001 - 缺少 pywin32 等情况下降级
    tray = None  # type: ignore[assignment]

__all__ = ["autostart", "hotkey", "icon", "tray"]
