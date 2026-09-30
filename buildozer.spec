[app]
title = QQ机器人
package.name = qqbot
package.domain = org.excuse
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json,txt,yaml,md
source.exclude_dirs = tests,bin,venv,.venv,__pycache__,data
version = 0.1.0
requirements = python3,kivy,aiohttp,pyyaml,qq-botpy

# 后台常驻服务：Bot 是服务名，service.py 是入口，:foreground 让它在 Android 8+
# 以前台服务运行（有常驻通知），显著减少被系统回收的概率
services = Bot:service.py:foreground

android.permissions = INTERNET,ACCESS_NETWORK_STATE,WAKE_LOCK,FOREGROUND_SERVICE,RECEIVE_BOOT_COMPLETED
android.api = 35
android.minapi = 26
# 只打 arm64：构建时间减半，覆盖绝大多数在用手机
android.archs = arm64-v8a
android.allow_backup = True
android.log_files = bot.log

# 只打 arm64 会把构建时间砍半，想覆盖更多老机器就保留上面两行
p4a.branch = master

orientation = portrait
fullscreen = 0
log_level = 2

[buildozer]
log_level = 2
warn_on_root = 0

# 说明：bot.log / status.txt 由 service.py 写入应用私有目录，不需要额外存储权限
