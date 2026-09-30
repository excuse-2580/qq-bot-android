"""Android 后台服务：常驻运行 QQ 机器人。

buildozer.spec 中通过 `services=Bot:service.py:foreground` 声明，
:foreground 让 p4a 以前台服务方式启动，避免被系统休眠策略杀掉。

桌面端不会加载本文件。
"""
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
os.chdir(HERE)

from core.config import config  # noqa: E402
from core.paths import data_dir  # noqa: E402

LOG_FILE = data_dir() / "bot.log"
_MAX_LOG = 300_000  # 日志超过 300KB 就截断，防止无限增长


class _Tee:
    """同时写文件和标准输出，方便 adb logcat 也能看到。"""

    def __init__(self, fp, orig):
        self.fp, self.orig = fp, orig

    def write(self, s):
        try:
            self.fp.write(s)
            self.fp.flush()
        except Exception:  # noqa: BLE001
            pass
        if self.orig is not None:
            try:
                self.orig.write(s)
                self.orig.flush()
            except Exception:  # noqa: BLE001
                pass
        return len(s)

    def flush(self):
        try:
            self.fp.flush()
        except Exception:  # noqa: BLE001
            pass


def _setup_log():
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    if LOG_FILE.exists() and LOG_FILE.stat().st_size > _MAX_LOG:
        LOG_FILE.write_text("", encoding="utf-8")
    fp = LOG_FILE.open("a", encoding="utf-8", errors="replace")
    sys.stdout = _Tee(fp, sys.stdout)
    sys.stderr = _Tee(fp, sys.stderr)


def _write_status(text: str) -> None:
    try:
        (data_dir() / "status.txt").write_text(text, encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def main() -> None:
    _setup_log()

    import botpy  # noqa: E402
    from bot import ChatBot, build_intents  # noqa: E402

    print("=" * 40)
    print("服务启动", time.strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 40)

    errs = config.validate()
    if errs:
        for e in errs:
            print("配置缺失：", e)
        _write_status("配置未完成：请在 App 里填写 AppID 和 AppSecret")
        return

    _write_status("连接中…")
    intents = build_intents()
    print(f"intents = {intents.value}")

    retry = 0
    while True:
        try:
            client = ChatBot(intents=intents, timeout=10, is_sandbox=config.sandbox)
            client.run(appid=config.appid, secret=config.secret)
            # run() 正常返回说明连接断开了
            retry += 1
            wait = min(60, 5 * retry)
            print(f"连接断开，{wait} 秒后第 {retry} 次重连…")
            _write_status(f"断开，{wait}s 后重连（第 {retry} 次）")
            time.sleep(wait)
        except KeyboardInterrupt:
            _write_status("已停止")
            break
        except Exception as e:  # noqa: BLE001
            retry += 1
            wait = min(120, 10 * retry)
            print(f"异常：{type(e).__name__}: {e}")
            print(f"{wait} 秒后第 {retry} 次重连…")
            _write_status(f"异常，{wait}s 后重连（第 {retry} 次）")
            time.sleep(wait)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        try:
            print(f"致命错误：{type(e).__name__}: {e}")
            _write_status(f"致命错误：{type(e).__name__}")
        except Exception:  # noqa: BLE001
            pass
