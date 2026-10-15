"""配置读写：%APPDATA%\\WinTimer\\settings.json。"""

import json
import os
import tempfile
from pathlib import Path

DEFAULTS = {
    "topmost": True,
    "mode": "stopwatch",          # stopwatch | countdown
    "countdown_hours": 0,
    "countdown_minutes": 5,
    "countdown_seconds": 0,
    "notify_toast": True,         # Windows 系统通知
    "notify_popup": False,        # 同时弹出置顶提醒窗 + 提示音
    "window_pos": "",             # 例如 "+900+40"
    "aumid_registered": False,    # 是否已写开始菜单快捷方式（系统通知需要）
}


def config_dir() -> Path:
    base = os.environ.get("APPDATA") or tempfile.gettempdir()
    path = Path(base) / "WinTimer"
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        path = Path(tempfile.gettempdir()) / "WinTimer"
        path.mkdir(parents=True, exist_ok=True)
    return path


def settings_path() -> Path:
    return config_dir() / "settings.json"


def load() -> dict:
    data = dict(DEFAULTS)
    try:
        with open(settings_path(), "r", encoding="utf-8") as fh:
            loaded = json.load(fh)
        if isinstance(loaded, dict):
            data.update({k: v for k, v in loaded.items() if k in DEFAULTS})
    except (OSError, ValueError):
        pass
    return data


def save(data: dict) -> None:
    payload = {k: data.get(k, v) for k, v in DEFAULTS.items()}
    try:
        with open(settings_path(), "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
    except OSError:
        pass
