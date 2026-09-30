"""规则回复引擎：命中关键词直接回复，优先于 AI。

data/rules.json 保存后热重载，无需重启机器人。
"""
from __future__ import annotations

import json
import random
import re
import time
from pathlib import Path
from typing import List, Optional

from .config import ROOT, config
from .paths import data_dir, project_root


class RuleEngine:
    def __init__(self, path: Optional[Path] = None) -> None:
        p = Path(config.rules_file)
        self.path = p if p.is_absolute() else (data_dir() / p.name)
        self._compiled: List[dict] = []
        self._mtime = 0.0
        self._bootstrap()
        self.load(force=True)

    def _bootstrap(self) -> None:
        """首次运行（尤其 Android）把内置规则复制到可写目录。"""
        if self.path.exists():
            return
        src = project_root() / Path(config.rules_file)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_bytes(src.read_bytes())
        except OSError:
            pass

    # ---------- 加载 ----------
    def load(self, force: bool = False) -> int:
        try:
            mtime = self.path.stat().st_mtime
        except (FileNotFoundError, OSError):
            if not self._compiled:
                print(f"[规则] 规则文件不存在：{self.path}")
            return len(self._compiled)
        if not force and mtime == self._mtime:
            return len(self._compiled)

        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"[规则] JSON 格式错误，沿用旧规则：{e}")
            return len(self._compiled)

        raw = data.get("rules", []) if isinstance(data, dict) else data
        compiled: List[dict] = []
        for item in raw:
            mode = item.get("match", "contains")
            if mode not in ("contains", "exact", "prefix", "regex"):
                print(f"[规则] 未知匹配模式 {mode}，按 contains 处理")
                mode = "contains"
            entry = {
                "keywords": [str(k) for k in item.get("keywords", [])],
                "reply": item.get("reply", ""),
                "mode": mode,
                "scope": item.get("scope", "all"),
                "pattern": None,
            }
            if mode == "regex":
                try:
                    entry["pattern"] = re.compile("|".join(entry["keywords"]), re.I)
                except re.error as e:
                    print(f"[规则] 正则编译失败，跳过：{e}")
                    continue
            if entry["reply"]:
                compiled.append(entry)

        self._compiled, self._mtime = compiled, mtime
        print(f"[规则] 已加载 {len(compiled)} 条规则")
        return len(compiled)

    # ---------- 匹配 ----------
    def find(self, text: str, scope: str, nickname: str = "你") -> Optional[str]:
        """scope: group / c2c / guild。命中返回回复文本，否则 None。"""
        self.load()
        if not self._compiled:
            return None

        t = (text or "").strip()
        if not t:
            return None
        low = t.lower()

        for r in self._compiled:
            s = r["scope"]
            if s not in ("all", scope):
                continue

            hit = False
            if r["mode"] == "regex":
                hit = bool(r["pattern"] and r["pattern"].search(t))
            else:
                for kw in r["keywords"]:
                    if r["mode"] == "exact":
                        if t == kw:
                            hit = True
                            break
                    elif r["mode"] == "prefix":
                        if low.startswith(kw.lower()):
                            hit = True
                            break
                    else:  # contains
                        if kw.lower() in low:
                            hit = True
                            break
            if hit:
                reply = r["reply"]
                if isinstance(reply, list):
                    reply = random.choice(reply) if reply else ""
                try:
                    return str(reply).format(nickname=nickname)
                except (KeyError, IndexError):
                    return str(reply)
        return None

    # 供测试使用
    @property
    def size(self) -> int:
        return len(self._compiled)


rule_engine = RuleEngine()
