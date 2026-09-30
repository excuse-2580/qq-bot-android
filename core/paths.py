"""统一路径：桌面端放项目目录，Android 放应用私有目录。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

IS_ANDROID = "android" in sys.modules or hasattr(sys, "getandroidapilevel")


def _root() -> Path:
    """项目根目录（含 bot.py / core/ 的那一层）。"""
    return Path(__file__).resolve().parents[1]


def data_dir() -> Path:
    """可写目录：Android 用应用私有存储，桌面用项目目录。"""
    if IS_ANDROID:
        try:
            from android.storage import app_storage_path  # type: ignore
            p = Path(app_storage_path())
        except Exception:  # noqa: BLE001
            p = Path(os.path.expanduser("~")) / ".qqbot"
        return p
    return _root() / "data"


def project_root() -> Path:
    return _root()


def ensure() -> Path:
    d = data_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d
