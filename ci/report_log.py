#!/usr/bin/env python3
"""把构建日志尾部推送到 logs 分支，方便在无法下载 artifact 时远程排查。

用法：python3 ci/report_log.py [success|failure]
"""
import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

TOKEN = os.environ["GITHUB_TOKEN"]
REPO = os.environ.get("GITHUB_REPOSITORY", "excuse-2580/qq-bot-android")
BRANCH = "logs"
LOG = "/home/runner/work/qq-bot-android/qq-bot-android/build.log"

H = {
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github+json",
    "Content-Type": "application/json",
    "User-Agent": "ci-log-reporter",
}


def api(method, path, payload=None, tries=3):
    data = json.dumps(payload).encode() if payload is not None else None
    last = None
    for _ in range(tries):
        try:
            r = urllib.request.Request(
                f"https://api.github.com{path}", data=data, method=method, headers=H)
            with urllib.request.urlopen(r, timeout=60) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            last = RuntimeError(f"{method} {path} → {e.code}: {e.read().decode()[:200]}")
            if e.code in (404, 409):
                break
        except Exception as e:  # noqa: BLE001
            last = e
        time.sleep(2)
    if last:
        raise last


def main() -> None:
    status = sys.argv[1] if len(sys.argv) > 1 else "failure"

    try:
        text = open(LOG, encoding="utf-8", errors="replace").read()
    except OSError as e:
        text = f"（无法读取 {LOG}：{e}）"

    lines = text.splitlines()
    tail = "\n".join(lines[-500:])
    body = (
        f"# 构建结果：{status}\n"
        f"# 时间：{time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}\n"
        f"# 运行：{os.environ.get('GITHUB_RUN_ID', '?')} "
        f"(第 {os.environ.get('GITHUB_RUN_NUMBER', '?')} 次)\n"
        f"# 提交：{os.environ.get('GITHUB_SHA', '?')}\n"
        f"# 总行数：{len(lines)}\n\n{tail}\n"
    )

    # 1) 确保 logs 分支存在
    try:
        api("GET", f"/repos/{REPO}/git/ref/heads/{BRANCH}")
    except Exception:  # noqa: BLE001
        main_ref = api("GET", f"/repos/{REPO}/git/ref/heads/main")
        api("POST", f"/repos/{REPO}/git/refs",
            {"ref": f"refs/heads/{BRANCH}", "sha": main_ref["object"]["sha"]})

    # 2) 写入/更新 build.log
    path = f"/repos/{REPO}/contents/ci-build.log?ref={BRANCH}"
    payload = {
        "message": f"CI 日志 · 第 {os.environ.get('GITHUB_RUN_NUMBER', '?')} 次 · {status}",
        "content": base64.b64encode(body.encode()).decode(),
        "branch": BRANCH,
    }
    try:
        cur = api("GET", path)
        payload["sha"] = cur["sha"]
    except Exception:  # noqa: BLE001
        pass
    api("PUT", f"/repos/{REPO}/contents/ci-build.log", payload)
    print(f"✓ 日志已推送到 {BRANCH} 分支（{len(lines)} 行中的最后 500 行）")

    # 3) 顺便把关键错误抓出来直接打到控制台
    keys = ("ERROR", "error:", "failed", "Failed", "Traceback", "Exception",
            "No matching", "not found", "command failed", "BUILD FAILURE")
    print("\n===== 日志中的关键行 =====")
    hits = [l for l in lines if any(k in l for k in keys)]
    for l in hits[:60]:
        print(" ", l[:220])
    if not hits:
        print("  （未匹配到明显错误行）")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        print(f"报告日志失败（不影响主流程）：{type(e).__name__}: {e}")
