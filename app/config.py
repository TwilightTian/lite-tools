"""应用配置：读写用户目录下的 config.json。"""

from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path
from typing import Any

APP_NAME = "LiteTools"
APP_TITLE = "Lite Tools"
APP_VERSION = "1.0.0"


def _config_root() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home())
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / APP_NAME


CONFIG_DIR = _config_root()
CONFIG_PATH = CONFIG_DIR / "config.json"

DEFAULTS: dict[str, Any] = {
    "window": {
        "width": 1120,
        "height": 740,
        "x": None,
        "y": None,
        "always_on_top": False,
        "last_page": "json",
    },
    "startup": {
        "auto_start": False,
        "start_minimized": False,
        "close_to_tray": False,
    },
    "hotkey": {
        "enabled": False,
        "modifiers": ["ctrl", "alt"],
        "key": "L",
    },
    "json": {
        "indent": 2,
        "sort_keys": False,
        "ensure_ascii": False,
        "lenient": True,
    },
    "time": {
        "zone_offset": "local",
        "zone": "本地时区",
        "auto_refresh": True,
    },
    "env": {
        "source": "IDEA",
        "target": "Linux export",
    },
    "codegen": {
        "class_name": "Root",
        "package": "com.example.model",
        "use_lombok": True,
        "use_jackson": True,
        "boxed": True,
        "depth": 3,
    },
    "net": {
        "timeout": 3.0,
        "public_ip_api": "https://api.ipify.org",
        "ping_count": 4,
        "ping_host": "www.baidu.com",
    },
}


class Config:
    """极简配置对象，支持 `a.b.c` 形式的点号路径读写。"""

    def __init__(self, path: Path | str = CONFIG_PATH) -> None:
        self.path = Path(path)
        self._data: dict[str, Any] = copy.deepcopy(DEFAULTS)
        self.load()

    # ---------------------------------------------------------------- io
    def load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if isinstance(raw, dict):
            _deep_merge(self._data, raw)

    def save(self) -> bool:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            return True
        except OSError:
            return False

    # ------------------------------------------------------------ access
    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self._data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, dotted: str, value: Any) -> None:
        parts = dotted.split(".")
        node = self._data
        for part in parts[:-1]:
            nxt = node.get(part)
            if not isinstance(nxt, dict):
                nxt = {}
                node[part] = nxt
            node = nxt
        node[parts[-1]] = value


def _deep_merge(base: dict[str, Any], extra: dict[str, Any]) -> None:
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


_config: Config | None = None


def get_config() -> Config:
    """全局单例配置。"""
    global _config
    if _config is None:
        _config = Config()
    return _config
