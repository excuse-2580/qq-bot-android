"""core 包：显式导出各模块单例，避免与子模块名混淆。"""

from .ai import AIClient, ai_client
from .memory import Memory, memory
from .passive import PassiveManager, passive
from .rules import RuleEngine, rule_engine

__all__ = [
    "AIClient", "ai_client",
    "Memory", "memory",
    "PassiveManager", "passive",
    "RuleEngine", "rule_engine",
]
