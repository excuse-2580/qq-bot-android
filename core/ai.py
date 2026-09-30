"""AI 大模型客户端：所有 OpenAI 兼容接口通用（DeepSeek / 通义 / Kimi / Ollama ...）。

刻意不依赖 openai SDK —— 它依赖 pydantic-core（Rust 编译），
在 Android / buildozer 环境下极易构建失败。这里直接用 aiohttp 发一个 POST 即可，
botpy 本身就依赖 aiohttp，等于零新增依赖。
"""
from __future__ import annotations

import json
from typing import List

import aiohttp

from .config import config


class AIClient:
    def __init__(self) -> None:
        if config.ai_api_key:
            print(f"[AI] 已启用：{config.ai_model} @ {config.ai_base_url}")
        else:
            print("[AI] 未配置 ai_api_key，机器人将只走规则回复")

    @property
    def enabled(self) -> bool:
        # 运行时读取：Android 上用户在界面保存密钥后重启服务即可生效
        return bool(config.ai_api_key)

    async def chat(self, history: List[dict]) -> str:
        """history 为已裁剪的 [{'role':'user'|'assistant','content':...}] 列表。"""
        if not self.enabled:
            raise RuntimeError("AI 未启用")

        url = config.ai_base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": config.ai_model,
            "messages": [
                {"role": "system", "content": config.ai_system_prompt},
                *history,
            ],
            "max_tokens": 1024,
            "temperature": 0.8,
        }
        headers = {
            "Authorization": f"Bearer {config.ai_api_key}",
            "Content-Type": "application/json",
        }
        timeout = aiohttp.ClientTimeout(total=config.ai_timeout)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    body = (await resp.text())[:200]
                    raise RuntimeError(f"HTTP {resp.status}：{body}")
                data = await resp.json(content_type=None)

        try:
            text = (data["choices"][0]["message"]["content"] or "").strip()
        except (KeyError, IndexError, TypeError):
            raise RuntimeError(f"返回体结构异常：{json.dumps(data)[:200]}")

        if not text:
            raise RuntimeError("模型返回了空内容")
        if len(text) > config.ai_max_reply:
            text = text[: config.ai_max_reply] + "\n…（内容较长已截断）"
        return self.plain(text)

    @staticmethod
    def plain(text: str) -> str:
        """QQ 里 Markdown 符号常显示异常，去掉常见标记，保留纯文本。"""
        for a, b in (("**", ""), ("__", ""), ("`", "")):
            text = text.replace(a, b)
        lines = [
            ln.lstrip("#").strip() if ln.lstrip().startswith("#") else ln
            for ln in text.splitlines()
        ]
        return "\n".join(lines).strip()


ai_client = AIClient()
