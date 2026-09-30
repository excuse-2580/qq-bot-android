"""配置加载：config.yaml 为主，环境变量可覆盖。

优先级：环境变量 > config.yaml > 默认值
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import yaml

from .paths import data_dir, project_root

ROOT = project_root()


def _env(key: str, default=None):
    v = os.environ.get(key)
    return v if v not in (None, "") else default


def _find_config() -> Path:
    """Android 上优先读应用私有目录，桌面端读项目目录。"""
    c = _env("BOT_CONFIG")
    if c:
        return Path(c)
    for base in (data_dir(), ROOT):
        for name in ("config.yaml", "config.yml"):
            p = base / name
            if p.exists():
                return p
    return data_dir() / "config.yaml"


CONFIG_PATH = _find_config()
_raw = {}
if CONFIG_PATH.exists():
    try:
        _raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001
        _raw = {}
if not isinstance(_raw, dict):
    _raw = {}


def save(updates: dict) -> None:
    """把配置写回 config.yaml（供 Android 界面保存凭证用）。"""
    merged = {**_raw, **updates}
    path = data_dir() / "config.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(merged, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _get(key: str, default=None, cast=str):
    """yaml / 环境变量 取值，环境变量用大写下划线形式。"""
    val = _raw.get(key, None)
    env_val = _env(key.upper(), None)
    if env_val is not None:
        val = env_val
    if val is None or val == "":
        return default
    try:
        if cast is bool:
            return str(val).lower() in ("1", "true", "yes", "on")
        if cast is int:
            return int(val)
        if cast is list:
            if isinstance(val, list):
                return val
            return [x.strip() for x in str(val).split(",") if x.strip()]
        return cast(val)
    except (TypeError, ValueError):
        return default


@dataclass
class Config:
    # ---- QQ 开放平台凭证 ----
    appid: str = ""
    secret: str = ""

    # ---- 监听范围 ----
    enable_group: bool = True          # 群聊 @机器人
    enable_c2c: bool = True            # 私聊 / 单聊
    enable_guild: bool = False         # 频道（@机器人 + 频道私信）
    sandbox: bool = False

    # ---- 规则 ----
    rules_file: str = "data/rules.json"

    # ---- AI ----
    ai_api_key: str = ""
    ai_base_url: str = "https://api.deepseek.com"
    ai_model: str = "deepseek-chat"
    ai_system_prompt: str = (
        "你是一个友好、简洁的中文聊天助手，回复控制在 3 句话以内，"
        "不要使用 Markdown 标题和表格，纯文本输出。"
    )
    ai_history_size: int = 12
    ai_history_ttl: int = 30       # 分钟
    ai_timeout: int = 60           # 秒
    ai_max_reply: int = 1500       # 字符

    # ---- 群聊触发 ----
    group_prefix: str = ""         # 群聊必须 @，额外前缀可选（content 已去 @ 前缀）

    # ---- 被动回复窗口（官方 API 硬限制）----
    group_passive_ttl: int = 300      # 群聊被动回复有效期 5 分钟
    group_passive_max: int = 5        # 每条消息最多回复 5 次
    c2c_passive_ttl: int = 3600       # 单聊被动回复有效期 60 分钟
    c2c_passive_max: int = 4          # 每条消息最多回复 4 次

    # ---- 去重 ----
    dedup_ttl: int = 600           # 同一消息去重窗口（秒）

    log_level: str = "INFO"

    def validate(self) -> List[str]:
        errs = []
        if not self.appid:
            errs.append("缺少 appid（QQ 开放平台 → 开发设置 → AppID）")
        if not self.secret:
            errs.append("缺少 secret（QQ 开放平台 → 开发设置 → AppSecret）")
        return errs


config = Config(
    appid=_get("appid", ""),
    secret=_get("secret", ""),
    enable_group=_get("enable_group", True, bool),
    enable_c2c=_get("enable_c2c", True, bool),
    enable_guild=_get("enable_guild", False, bool),
    sandbox=_get("sandbox", False, bool),
    rules_file=_get("rules_file", "data/rules.json"),
    ai_api_key=_get("ai_api_key", ""),
    ai_base_url=_get("ai_base_url", "https://api.deepseek.com"),
    ai_model=_get("ai_model", "deepseek-chat"),
    ai_system_prompt=_get(
        "ai_system_prompt",
        "你是一个友好、简洁的中文聊天助手，回复控制在 3 句话以内，"
        "不要使用 Markdown 标题和表格，纯文本输出。",
    ),
    ai_history_size=_get("ai_history_size", 12, int),
    ai_history_ttl=_get("ai_history_ttl", 30, int),
    ai_timeout=_get("ai_timeout", 60, int),
    ai_max_reply=_get("ai_max_reply", 1500, int),
    group_prefix=_get("group_prefix", ""),
    group_passive_ttl=_get("group_passive_ttl", 300, int),
    group_passive_max=_get("group_passive_max", 5, int),
    c2c_passive_ttl=_get("c2c_passive_ttl", 3600, int),
    c2c_passive_max=_get("c2c_passive_max", 4, int),
    dedup_ttl=_get("dedup_ttl", 600, int),
    log_level=_get("log_level", "INFO"),
)
