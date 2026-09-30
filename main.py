"""安卓端 Kivy 界面：填凭证、启停后台服务、看日志。

桌面端不加载本文件（python bot.py 走命令行）。
"""
import os
import sys
from pathlib import Path

from kivy.app import App
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.core.window import Window

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from core.config import CONFIG_PATH, config, save  # noqa: E402
from core.paths import data_dir  # noqa: E402

Window.softinput_mode = "resize"

BG = (0.10, 0.11, 0.13, 1)
CARD = (0.16, 0.17, 0.20, 1)
ACCENT = (0.24, 0.56, 0.94, 1)
GREEN = (0.22, 0.68, 0.42, 1)
RED = (0.78, 0.28, 0.28, 1)


def _read_status() -> str:
    f = data_dir() / "status.txt"
    try:
        return f.read_text(encoding="utf-8").strip() or "未启动"
    except Exception:  # noqa: BLE001
        return "未启动"


def _read_log(tail: int = 6000) -> str:
    f = data_dir() / "bot.log"
    try:
        txt = f.read_text(encoding="utf-8", errors="replace")
        return txt[-tail:] if len(txt) > tail else txt
    except Exception:  # noqa: BLE001
        return "（暂无日志）"


class Root(BoxLayout):
    def __init__(self, **kw):
        super().__init__(orientation="vertical", padding=14, spacing=10, **kw)

        self.add_widget(Label(
            text="QQ 官方机器人", font_size="20sp", bold=True,
            size_hint_y=None, height=44, color=(1, 1, 1, 1),
        ))
        self.status = Label(
            text=f"状态：{_read_status()}", size_hint_y=None, height=32,
            color=(0.8, 0.85, 0.9, 1), font_size="13sp",
        )
        self.add_widget(self.status)

        self.add_widget(self._field("AppID（QQ 开放平台 → 开发设置）", config.appid, "appid"))
        self.add_widget(self._field("AppSecret", config.secret, "secret", password=True))
        self.add_widget(self._field("AI Key（可选，留空只走规则）", config.ai_api_key, "ai", password=True))

        btns = BoxLayout(size_hint_y=None, height=52, spacing=10)
        self.btn_save = Button(text="保存配置", background_color=ACCENT)
        self.btn_save.bind(on_press=self.do_save)
        self.btn_run = Button(text="启动服务", background_color=GREEN)
        self.btn_run.bind(on_press=self.do_toggle)
        btns.add_widget(self.btn_save)
        btns.add_widget(self.btn_run)
        self.add_widget(btns)

        self.tip = Label(
            text="", size_hint_y=None, height=28, font_size="12sp", color=(1, 0.85, 0.4, 1),
        )
        self.add_widget(self.tip)

        self.log = TextInput(
            text=_read_log(), readonly=True, font_size="11sp",
            background_color=(0.07, 0.08, 0.10, 1), foreground_color=(0.75, 0.85, 0.78, 1),
            font_name="RobotoMono-Regular" if self._mono() else "Roboto",
        )
        sc = ScrollView()
        sc.add_widget(self.log)
        self.add_widget(sc)

        Clock.schedule_interval(self.refresh, 2.0)

    @staticmethod
    def _mono() -> bool:
        return False

    def _field(self, hint: str, value: str, key: str, password: bool = False):
        box = BoxLayout(size_hint_y=None, height=60, spacing=6)
        box.add_widget(Label(text=hint, size_hint_x=None, width=140,
                             font_size="11sp", color=(0.7, 0.75, 0.8, 1),
                             text_size=(136, None), halign="left"))
        ti = TextInput(
            text=value or "", multiline=False, password=password,
            background_color=CARD, foreground_color=(1, 1, 1, 1), font_size="13sp",
        )
        setattr(self, f"in_{key}", ti)
        box.add_widget(ti)
        return box

    # ---------------- 操作 ----------------
    def do_save(self, *_):
        try:
            save({
                "appid": self.in_appid.text.strip(),
                "secret": self.in_secret.text.strip(),
                "ai_api_key": self.in_ai.text.strip(),
            })
            self.tip.text = f"已保存到 {data_dir() / 'config.yaml'}"
            self.tip.color = (0.5, 0.9, 0.6, 1)
        except Exception as e:  # noqa: BLE001
            self.tip.text = f"保存失败：{type(e).__name__}"
            self.tip.color = (1, 0.5, 0.5, 1)

    def do_toggle(self, *_):
        if self.btn_run.text == "启动服务":
            self._start()
        else:
            self._stop()

    def _start(self, *_):
        self.do_save()
        try:
            from jnius import autoclass
            Activity = autoclass("org.kivy.android.PythonActivity")
            Service = autoclass("org.kivy.android.PythonService")
            Service.start(Activity.mActivity, "")
            self.btn_run.text = "停止服务"
            self.btn_run.background_color = RED
            self.tip.text = "服务已启动，建议在系统设置里关闭本应用的电池优化"
            self.tip.color = (0.5, 0.9, 0.6, 1)
        except Exception as e:  # noqa: BLE001
            self.tip.text = f"启动失败：{type(e).__name__}: {e}"
            self.tip.color = (1, 0.5, 0.5, 1)

    def _stop(self, *_):
        try:
            from jnius import autoclass
            Activity = autoclass("org.kivy.android.PythonActivity")
            Service = autoclass("org.kivy.android.PythonService")
            Intent = autoclass("android.content.Intent")
            Activity.mActivity.stopService(Intent(Activity.mActivity, Service))
            self.btn_run.text = "启动服务"
            self.btn_run.background_color = GREEN
            self.tip.text = "已停止"
            self.tip.color = (0.8, 0.8, 0.8, 1)
        except Exception as e:  # noqa: BLE001
            self.tip.text = f"停止失败：{type(e).__name__}"
            self.tip.color = (1, 0.5, 0.5, 1)

    def refresh(self, *_):
        self.status.text = f"状态：{_read_status()}"
        new = _read_log()
        if new != self.log.text:
            self.log.text = new
            self.log.cursor = (0, 0)


class BotApp(App):
    def build(self):
        self.title = "QQ 机器人"
        return Root()

    def on_pause(self):
        return True  # 切后台不杀进程


if __name__ == "__main__":
    BotApp().run()
