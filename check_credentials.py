#!/usr/bin/env python3
"""凭证有效性验证：换取 access_token 并查询机器人信息。

只在排错时手动运行，用完请删除或清空其中的密钥输出。
"""
import json
import urllib.request

from core.config import config

APPID = config.appid
SECRET = config.secret


def post(url: str, payload: dict, headers: dict | None = None):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:400]
    except Exception as e:
        return -1, f"{type(e).__name__}: {e}"


def mask(s: str, head: int = 4, tail: int = 4) -> str:
    if not s or len(s) <= head + tail:
        return "*" * len(s) if s else "(空)"
    return f"{s[:head]}{'*' * (len(s) - head - tail)}{s[-tail:]}"


print(f"appid = {APPID}")
print(f"secret = {mask(SECRET)}  (长度 {len(SECRET)})\n")

print("[1] 换取 access_token ...")
code, data = post(
    "https://bots.qq.com/app/getAppAccessToken",
    {"appId": APPID, "clientSecret": SECRET},
)
print(f"    HTTP {code}")
if code == 200 and isinstance(data, dict) and "access_token" in data:
    token = data["access_token"]
    print(f"    ✓ 鉴权成功  token={mask(token)}  expires_in={data.get('expires_in')}")
else:
    print(f"    ✗ 鉴权失败：{data}")
    raise SystemExit(1)

print("\n[2] 查询机器人信息 /users/@me ...")
code2, info = post(
    "https://api.sgroup.qq.com/v2/users/@me", {},
    headers={"Authorization": f"QQBot {token}"},
)
print(f"    HTTP {code2}: {info}")

print("\n[3] 查询可连接的 WebSocket 网关 /gateway ...")
req = urllib.request.Request(
    "https://api.sgroup.qq.com/gateway",
    headers={"Authorization": f"QQBot {token}"},
)
try:
    with urllib.request.urlopen(req, timeout=15) as r:
        print(f"    HTTP {r.status}: {r.read().decode()[:300]}")
except Exception as e:
    print(f"    失败：{type(e).__name__}: {e}")
