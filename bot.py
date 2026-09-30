"""QQ 官方机器人（QQ 开放平台 / botpy）。

消息进来 → 规则优先命中 → 没命中交给大模型兜底。
同时严格遵守官方 API 的被动回复窗口限制（群聊 5 分钟 5 次、单聊 60 分钟 4 次）。

启动：python bot.py
"""
from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

import botpy
from botpy import logging as botpy_logging
from botpy.message import C2CMessage, DirectMessage, GroupMessage, Message

from core import ai_client, memory, passive, rule_engine
from core.config import Config, config

_log = botpy_logging.get_logger()

SEG_LIMIT = 1200  # 单条消息字符上限，超出分段发送（每段消耗一次被动配额）


# ------------------------- 消息上下文 -------------------------
@dataclass
class Ctx:
    scope: str                                    # group / c2c / guild
    msg_id: str
    msg_seq: Optional[int]
    text: str
    session_key: str
    sender: str                                   # 用于规则里 {nickname} 的短标识
    raw_send: Callable[..., Awaitable]            # 底层发送（已绑定目标）
    use_passive: bool = True                      # 频道不需要 msg_seq 管理


def _short(openid: Optional[str]) -> str:
    """openid 太长，取末尾 6 位当作可读标识。"""
    if not openid:
        return "你"
    return f"…{openid[-6:]}"


def split_text(text: str, limit: int = SEG_LIMIT) -> list:
    """按段落切分长文本，尽量不在句子中间断开。"""
    if len(text) <= limit:
        return [text]
    parts, cur = [], ""
    for para in text.split("\n"):
        while len(para) > limit:
            if cur:
                parts.append(cur)
                cur = ""
            parts.append(para[:limit])
            para = para[limit:]
        if cur and len(cur) + len(para) + 1 > limit:
            parts.append(cur)
            cur = para
        else:
            cur = f"{cur}\n{para}" if cur else para
    if cur:
        parts.append(cur)
    return parts


# ------------------------- 机器人主体 -------------------------
class ChatBot(botpy.Client):
    async def on_ready(self) -> None:
        _log.info(f"[就绪] 机器人 {self.robot.name} 已上线")
        _log.info(
            f"[就绪] 监听范围：群聊={config.enable_group} "
            f"单聊={config.enable_c2c} 频道={config.enable_guild}"
        )
        _log.info(f"[就绪] 规则 {rule_engine.size} 条 ｜ AI={'开' if ai_client.enabled else '关'}")

    # ---------- 群聊 @机器人 ----------
    async def on_group_at_message_create(self, message: GroupMessage) -> None:
        await self._handle(
            Ctx(
                scope="group",
                msg_id=message.id,
                msg_seq=getattr(message, "msg_seq", None),
                text=message.content or "",
                session_key=f"g:{message.group_openid}:{message.author.member_openid}",
                sender=_short(message.author.member_openid),
                raw_send=lambda **kw: self.api.post_group_message(
                    group_openid=message.group_openid, **kw
                ),
            )
        )

    # ---------- 单聊 / 私聊 ----------
    async def on_c2c_message_create(self, message: C2CMessage) -> None:
        await self._handle(
            Ctx(
                scope="c2c",
                msg_id=message.id,
                msg_seq=getattr(message, "msg_seq", None),
                text=message.content or "",
                session_key=f"c:{message.author.user_openid}",
                sender=_short(message.author.user_openid),
                raw_send=lambda **kw: self.api.post_c2c_message(
                    openid=message.author.user_openid, **kw
                ),
            )
        )

    # ---------- 频道 @机器人 ----------
    async def on_at_message_create(self, message: Message) -> None:
        await self._handle(
            Ctx(
                scope="guild",
                msg_id=message.id,
                msg_seq=None,
                text=message.content or "",
                session_key=f"ch:{message.channel_id}",
                sender="你",
                raw_send=lambda **kw: message.reply(**kw),
                use_passive=False,
            )
        )

    # ---------- 频道私信 ----------
    async def on_direct_message_create(self, message: DirectMessage) -> None:
        await self._handle(
            Ctx(
                scope="guild",
                msg_id=message.id,
                msg_seq=None,
                text=message.content or "",
                session_key=f"dm:{message.guild_id}",
                sender="你",
                raw_send=lambda **kw: message.reply(**kw),
                use_passive=False,
            )
        )

    # ------------------------- 统一处理 -------------------------
    async def _handle(self, ctx: Ctx) -> None:
        # 1) 平台为保证可达会重复推送，先去重
        if ctx.use_passive and passive.is_duplicate(ctx.msg_id, ctx.msg_seq):
            _log.debug(f"[去重] 忽略重复推送 {ctx.msg_id}")
            return

        text = (ctx.text or "").strip()
        if not text:
            return

        # 2) 内置指令
        if text.lstrip("/").lower() in ("clear", "清空", "重置", "清空上下文"):
            memory.clear(ctx.session_key)
            await memory.save()
            await self._send(ctx, "上下文已清空，我们重新开始～")
            return

        # 3) 规则优先
        hit = rule_engine.find(text, ctx.scope, ctx.sender)
        if hit:
            _log.info(f"[规则] 命中：{text[:30]}")
            await self._send_all(ctx, hit)
            return

        # 4) AI 兜底
        if not ai_client.enabled:
            await self._send(ctx, "我还没学会这句话，你可以换个问法～")
            return
        await self._ask_ai(ctx, text)

    async def _ask_ai(self, ctx: Ctx, question: str) -> None:
        history = memory.get(ctx.session_key)
        history.append({"role": "user", "content": question})
        memory.trim(history)

        try:
            answer = await asyncio.wait_for(
                ai_client.chat(history), timeout=config.ai_timeout + 10
            )
        except asyncio.TimeoutError:
            history.pop()
            _log.warning("[AI] 响应超时")
            await self._send(ctx, "我想太久了，稍后再问我一次吧～")
            return
        except Exception as e:  # noqa: BLE001
            history.pop()
            _log.error(f"[AI] 调用失败：{type(e).__name__}: {e}")
            await self._send(ctx, f"脑子有点卡，稍后再试试（{type(e).__name__}）")
            return

        history.append({"role": "assistant", "content": answer})
        memory.trim(history)
        await memory.save()
        await self._send_all(ctx, answer)

    # ------------------------- 发送（含配额管理）-------------------------
    async def _send(self, ctx: Ctx, content: str) -> bool:
        """发送单条。返回是否成功。"""
        content = (content or "").strip()
        if not content:
            return False

        if not ctx.use_passive:
            try:
                await ctx.raw_send(content=content)
                return True
            except Exception as e:  # noqa: BLE001
                _log.error(f"[发送] 失败：{type(e).__name__}: {e}")
                return False

        ok, reason = passive.can_reply(ctx.msg_id, ctx.scope)
        if not ok:
            _log.warning(f"[被动窗口] {reason}（msg_id={ctx.msg_id}）")
            return False

        seq = passive.next_seq(ctx.msg_id)  # 同一 msg_id 必须递增
        try:
            await ctx.raw_send(content=content, msg_id=ctx.msg_id, msg_seq=seq)
            return True
        except Exception as e:  # noqa: BLE001
            passive.release(ctx.msg_id)  # 失败回滚，别白扣配额
            _log.error(f"[发送] 失败：{type(e).__name__}: {e}")
            return False

    async def _send_all(self, ctx: Ctx, content: str) -> None:
        """长文本分段发送，每段消耗一次被动配额；配额不够则截断提示。"""
        parts = split_text(content)
        for i, part in enumerate(parts):
            ok = await self._send(ctx, part)
            if not ok:
                if i > 0:
                    _log.warning("[发送] 被动配额用尽，后续分段被丢弃")
                return


# ------------------------- 启动 -------------------------
def build_intents() -> "botpy.Intents":
    intents = botpy.Intents.none()
    if config.enable_group or config.enable_c2c:
        intents.public_messages = True          # 1<<25 群聊 + 单聊事件
    if config.enable_guild:
        intents.public_guild_messages = True    # 1<<30 频道 @消息
        intents.direct_message = True           # 1<<12 频道私信
    return intents


def main() -> int:
    errs = config.validate()
    if errs:
        print("配置不完整：")
        for e in errs:
            print("  -", e)
        print("\n请执行：cp config.yaml.example config.yaml  然后填入 appid / secret")
        return 1

    intents = build_intents()
    _log.info(f"[启动] intents = {intents.value}")
    client = ChatBot(
        intents=intents,
        timeout=10,               # websocket 连接超时，与 AI 超时无关
        is_sandbox=config.sandbox,
    )
    client.run(appid=config.appid, secret=config.secret)
    return 0


if __name__ == "__main__":
    sys.exit(main())
