"""被动回复窗口管理 + 消息去重。

这是 QQ 官方 API 特有的硬性约束，用第三方协议框架时不存在，必须自己管：

    场景        被动回复有效期    每条消息最多回复
    群聊 @      5 分钟            5 次
    单聊        60 分钟           4 次

超时或用尽配额后，带 msg_id 的被动回复会被平台拒绝，只能走主动消息
（而主动消息配额极紧：群聊/单聊每月仅 4 条），所以这里选择直接提示用户重新发起。

另一个坑：平台为保证可达会重复推送同一条消息，需自行去重；
且同一 msg_id 多次回复时 msg_seq 必须递增，重复的 (msg_id, msg_seq) 会发送失败。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from .config import config


@dataclass
class _Window:
    """单条用户消息的被动回复配额。"""
    count: int = 0
    first_at: float = field(default_factory=time.time)


class PassiveManager:
    def __init__(self) -> None:
        self._windows: Dict[str, _Window] = {}
        self._seen: Dict[str, float] = {}

    # ---------- 去重 ----------
    def is_duplicate(self, msg_id: str, msg_seq=None) -> bool:
        """平台可能重复推送同一消息，用 (msg_id, msg_seq) 判定。"""
        key = f"{msg_id}:{msg_seq if msg_seq is not None else ''}"
        now = time.time()
        self._gc(now)
        if key in self._seen:
            return True
        self._seen[key] = now
        return False

    # ---------- 被动窗口 ----------
    @staticmethod
    def limits(scope: str) -> Tuple[int, int]:
        """返回 (有效期秒, 最多回复次数)。"""
        if scope == "group":
            return config.group_passive_ttl, config.group_passive_max
        return config.c2c_passive_ttl, config.c2c_passive_max

    def can_reply(self, msg_id: str, scope: str) -> Tuple[bool, str]:
        """是否还能用这条 msg_id 被动回复。"""
        ttl, max_n = self.limits(scope)
        w = self._windows.get(msg_id)
        if w is None:
            return True, ""
        if time.time() - w.first_at > ttl:
            return False, f"被动回复窗口已过期（{ttl // 60} 分钟），请重新 @ 我一次"
        if w.count >= max_n:
            return False, f"这条消息已回复 {max_n} 次，达到上限，请重新 @ 我一次"
        return True, ""

    def next_seq(self, msg_id: str) -> int:
        """同一 msg_id 的第 n 次回复需要递增的 msg_seq（从 1 开始）。"""
        w = self._windows.setdefault(msg_id, _Window())
        w.count += 1
        return w.count

    def remaining(self, msg_id: str, scope: str) -> int:
        _, max_n = self.limits(scope)
        w = self._windows.get(msg_id)
        return max_n - (w.count if w else 0)

    def release(self, msg_id: str) -> None:
        """回复失败时回滚计数，避免白白消耗配额。"""
        w = self._windows.get(msg_id)
        if w and w.count > 0:
            w.count -= 1

    # ---------- 清理 ----------
    def _gc(self, now: float) -> None:
        if len(self._seen) > 2000:
            for k, t in list(self._seen.items()):
                if now - t > config.dedup_ttl:
                    self._seen.pop(k, None)
        if len(self._windows) > 2000:
            for k, w in list(self._windows.items()):
                if now - w.first_at > config.c2c_passive_ttl:
                    self._windows.pop(k, None)


passive = PassiveManager()
