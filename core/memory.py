"""会话记忆：每个会话独立上下文，带过期与条数裁剪。"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Dict, List

from .config import config
from .paths import data_dir

SESSION_FILE = data_dir() / "sessions.json"


class Memory:
    def __init__(self) -> None:
        self._sessions: Dict[str, dict] = {}
        self._last_save = 0.0
        self._lock = asyncio.Lock()
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self._sessions.update(data)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass

    def _save(self) -> None:
        # 节流：3 秒内不重复写盘
        if time.time() - self._last_save < 3:
            return
        self._last_save = time.time()
        try:
            SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
            SESSION_FILE.write_text(
                json.dumps(self._sessions, ensure_ascii=False), encoding="utf-8"
            )
        except OSError as e:
            print(f"[记忆] 持久化失败：{e}")

    async def save(self) -> None:
        async with self._lock:
            self._save()

    def get(self, key: str) -> List[dict]:
        now = time.time()
        s = self._sessions.get(key)
        if s and now - s.get("ts", 0) > config.ai_history_ttl * 60:
            self._sessions.pop(key, None)
            s = None
        if not s:
            s = self._sessions[key] = {"messages": [], "ts": now}
        s["ts"] = now
        return s["messages"]

    @staticmethod
    def trim(history: List[dict]) -> None:
        if len(history) > config.ai_history_size:
            del history[: len(history) - config.ai_history_size]
        while history and history[0]["role"] != "user":
            history.pop(0)

    def clear(self, key: str) -> bool:
        existed = key in self._sessions
        self._sessions.pop(key, None)
        if existed:
            self._last_save = 0.0
        return existed


memory = Memory()
