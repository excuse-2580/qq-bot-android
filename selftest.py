#!/usr/bin/env python3
"""逻辑自检：不联网、不连 QQ，验证规则匹配 / 被动窗口 / 去重 / 分段 / intents。

运行：python selftest.py
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import botpy

from bot import Ctx, ChatBot, build_intents, split_text
from core import passive, rule_engine
from core.config import config

OK = FAIL = 0


def check(name: str, got, want=None, truthy: bool = False) -> None:
    global OK, FAIL
    passed = bool(got) if truthy else (got == want)
    if passed:
        OK += 1
        print(f"  ✓ {name}" + ("" if truthy else f"  → {got!r}"))
    else:
        FAIL += 1
        print(f"  ✗ {name}  期望={want!r} 实际={got!r}")


# ---------------------------------------------------------------- 规则
print("\n[1] 规则加载与匹配")
check("规则条数", rule_engine.size, 6)
check("你好 → 命中", rule_engine.find("你好", "group"), truthy=True)
check("HI 大写 → 命中", rule_engine.find("HI", "c2c"), truthy=True)
check("无关内容 → 不命中", rule_engine.find("今天中午吃什么", "group"), None)
check("exact 菜单 → 命中", rule_engine.find("菜单", "c2c"), truthy=True)
check("exact 菜单呢 → 不命中", rule_engine.find("菜单呢", "c2c"), None)
check("regex 早上好 → 命中", rule_engine.find("早上好大家", "group"), truthy=True)

print("\n[2] scope 隔离（关键：群聊/单聊规则互不串台）")
check("晚安(仅 c2c) 在 c2c → 命中", rule_engine.find("晚安", "c2c"), truthy=True)
check("晚安(仅 c2c) 在 group → 不命中", rule_engine.find("晚安", "group"), None)
check("早上好(仅 group) 在 group → 命中", rule_engine.find("早上好", "group"), truthy=True)
check("早上好(仅 group) 在 c2c → 不命中", rule_engine.find("早上好", "c2c"), None)
check("空文本 → 不命中", rule_engine.find("   ", "group"), None)
_outs = [rule_engine.find("你好", "group", "小明") for _ in range(12)]
check("{nickname} 占位符已被替换", all("{nickname}" not in o for o in _outs), True)
check("昵称确实替换进去了", any("小明" in o for o in _outs), True)

# ---------------------------------------------------------------- 被动窗口
print("\n[3] 被动回复窗口（群聊 5 分钟 / 5 次）")
passive._windows.clear()
mid = "msg_group_1"
check("初始可回复", passive.can_reply(mid, "group"), (True, ""))
seqs = [passive.next_seq(mid) for _ in range(5)]
check("msg_seq 递增", seqs, [1, 2, 3, 4, 5])
ok, reason = passive.can_reply(mid, "group")
check("第 6 次被拒", ok, False)
check("拒绝原因含上限", "上限" in reason, True)

passive.release(mid)
check("release 回滚后可再发一次", passive.can_reply(mid, "group"), (True, ""))

print("\n[4] 被动回复窗口（单聊 60 分钟 / 4 次）")
mid2 = "msg_c2c_1"
check("单聊第 1-4 次可回复", [passive.next_seq(mid2) for _ in range(4)], [1, 2, 3, 4])
check("单聊第 5 次被拒", passive.can_reply(mid2, "c2c")[0], False)

print("\n[5] 窗口过期")
mid3 = "msg_expire"
passive.next_seq(mid3)
passive._windows[mid3].first_at = time.time() - 301  # 群聊 300s 已过
check("超过 5 分钟 → 拒绝", passive.can_reply(mid3, "group")[0], False)
mid4 = "msg_c2c_ok"
passive.next_seq(mid4)
passive._windows[mid4].first_at = time.time() - 301
check("单聊 301 秒仍在窗口内", passive.can_reply(mid4, "c2c")[0], True)

# ---------------------------------------------------------------- 去重
print("\n[6] 消息去重")
passive._seen.clear()
check("首次推送 → 不重复", passive.is_duplicate("m1", 100), False)
check("相同 (id,seq) 再推 → 重复", passive.is_duplicate("m1", 100), True)
check("相同 id 不同 seq → 视为新消息", passive.is_duplicate("m1", 101), False)

# ---------------------------------------------------------------- 分段
print("\n[7] 长文本分段")
check("短文本不分段", split_text("你好"), ["你好"])
parts = split_text("\n".join([f"第{i}段" + "字" * 300 for i in range(10)]))
check("长文本被分段", len(parts) > 1, True)
check("每段不超上限", all(len(p) <= 1200 for p in parts), True)
check("拼接后不丢内容", "第0段" in "".join(parts) and "第9段" in "".join(parts), True)

# ---------------------------------------------------------------- intents
print("\n[8] intents 构造")
i_all = build_intents()
check("群聊/单聊位 1<<25 已置位", bool(i_all.value & (1 << 25)), True)

config.enable_guild = True
i_guild = build_intents()
check("频道位 1<<30 已置位", bool(i_guild.value & (1 << 30)), True)
check("频道私信位 1<<12 已置位", bool(i_guild.value & (1 << 12)), True)
config.enable_guild = False

# ---------------------------------------------------------------- 发送链路
print("\n[9] 发送链路（模拟被动配额耗尽后的行为）")
sent = []
fail_at = {"n": 0}


async def fake_send(**kw):
    """记录每次发送携带的 msg_id / msg_seq。"""
    fail_at["n"] += 1
    sent.append(kw)
    if fail_at["n"] == 2:
        raise RuntimeError("模拟接口报错")
    return True


bot = ChatBot(intents=botpy.Intents.none())
ctx = Ctx(
    scope="group", msg_id="send_test", msg_seq=1, text="",
    session_key="k", sender="x", raw_send=fake_send,
)
passive._windows.clear()
res = asyncio.run(bot._send(ctx, "第一条"))
check("发送成功", res, True)
check("携带 msg_id", sent[0].get("msg_id"), "send_test")
check("msg_seq 从 1 开始", sent[0].get("msg_seq"), 1)

res2 = asyncio.run(bot._send(ctx, "第二条（会失败）"))
check("接口报错 → 返回 False", res2, False)
check("失败后配额回滚（仍剩 4 次）", passive.remaining("send_test", "group"), 4)


async def multi():
    for _ in range(10):
        await bot._send(ctx, "x")


asyncio.run(multi())
check("连续发送后配额耗尽", passive.remaining("send_test", "group"), 0)

print("\n[10] 频道场景不走被动配额")
sent2 = []


async def guild_send(**kw):
    sent2.append(kw)
    return True


gctx = Ctx(scope="guild", msg_id="g1", msg_seq=None, text="",
           session_key="k", sender="x", raw_send=guild_send, use_passive=False)
asyncio.run(bot._send(gctx, "频道消息"))
check("频道发送不带 msg_seq", "msg_seq" not in sent2[0], True)
check("频道发送不带 msg_id", "msg_id" not in sent2[0], True)

print("\n" + "=" * 44)
print(f"通过 {OK} 项，失败 {FAIL} 项")
print("=" * 44)
sys.exit(1 if FAIL else 0)
