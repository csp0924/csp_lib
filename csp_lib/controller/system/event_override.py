# =============== Event-Driven Override ===============
#
# 事件驅動的 Override 協定與內建實現
#
# Protocol:
#   - EventDrivenOverride: 條件驅動的自動 push/pop override
#
# 內建實現:
#   - AlarmStopOverride: 告警自動停機（取代硬編碼的 _handle_auto_stop）
#   - ContextKeyOverride: 通用 context key 觸發

from __future__ import annotations

from typing import Any, Callable, Protocol, runtime_checkable

from csp_lib.controller.core import StrategyContext


@runtime_checkable
class EventDrivenOverride(Protocol):
    """
    事件驅動的 Override 協定

    SystemController 在每個執行週期評估 should_activate()。
    當條件滿足時自動 push_override()，條件解除 + cooldown 後自動 pop_override()。
    """

    @property
    def name(self) -> str:
        """對應 ModeManager 中的已註冊模式名稱"""
        ...

    @property
    def cooldown_seconds(self) -> float:
        """條件解除後的冷卻時間（防抖動）"""
        ...

    def should_activate(self, context: StrategyContext) -> bool:
        """評估是否應啟用此 override"""
        ...


class AlarmStopOverride:
    """
    告警自動停機

    取代硬編碼的 _handle_auto_stop()。
    當 context.extra[alarm_key] 為 True 時啟用 override。
    """

    def __init__(self, name: str = "__auto_stop__", alarm_key: str = "system_alarm") -> None:
        self._name = name
        self._alarm_key = alarm_key

    @property
    def name(self) -> str:
        return self._name

    @property
    def cooldown_seconds(self) -> float:
        return 0.0

    def should_activate(self, context: StrategyContext) -> bool:
        return context.extra.get(self._alarm_key, False) is True


class ContextKeyOverride:
    """
    通用：根據 context.extra 中的 key 值觸發 override

    用途範例：
    - ACB 跳脫 → 進入 islanding
    - 頻率偏差過大 → 進入 FP 模式
    - 外部信號觸發 → 進入特定模式
    """

    def __init__(
        self,
        name: str,
        context_key: str,
        activate_when: Callable[[Any], bool],
        cooldown_seconds: float = 5.0,
    ) -> None:
        self._name = name
        self._context_key = context_key
        self._activate_when = activate_when
        self._cooldown_seconds = cooldown_seconds

    @property
    def name(self) -> str:
        return self._name

    @property
    def cooldown_seconds(self) -> float:
        return self._cooldown_seconds

    def should_activate(self, context: StrategyContext) -> bool:
        value = context.extra.get(self._context_key)
        if value is None:
            return False
        return self._activate_when(value)
