[app]
title = QQ机器人
package.name = qqbot
package.domain = org.excuse
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json,txt,yaml,md
source.exclude_dirs = tests,bin,venv,.venv,__pycache__,ci,.github
source.exclude_patterns = _*.py,check_credentials.py,selftest.py
version = 0.1.0

# 依赖刻意精简：不用 openai SDK（依赖 Rust 编译的 pydantic-core，安卓构建易失败）
requirements = python3,kivy,aiohttp,pyyaml,qq-botpy

# 后台常驻服务：Bot 是服务名，service.py 是入口
# :foreground 让它在 Android 8+ 以前台服务运行（带常驻通知），大幅降低被系统回收概率
services = Bot:service.py:foreground

android.permissions = INTERNET,ACCESS_NETWORK_STATE,WAKE_LOCK,FOREGROUND_SERVICE,RECEIVE_BOOT_COMPLETED

# API 34 是目前 p4a 支持最完善的版本，35 容易出现 SDK 工具链不匹配
android.api = 34
android.minapi = 26
# 只打 arm64：构建时间减半，覆盖绝大多数在用手机
android.archs = arm64-v8a
android.allow_backup = True

p4a.branch = master

orientation = portrait
fullscreen = 0
log_level = 2

[buildozer]
log_level = 2
warn_on_root = 0
