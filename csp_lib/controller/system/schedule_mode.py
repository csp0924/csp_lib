# =============== Schedule Mode Controller Protocol ===============
#
# 排程模式控制協定
#
# 橋接 ScheduleService (L5) 與 SystemController (L6)：
#   - ScheduleModeController: Protocol 定義排程模式啟停介面

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from csp_lib.controller.core import Strategy


@runtime_checkable
class ScheduleModeController(Protocol):
    """
    排程模式控制協定

    橋接 ScheduleService (Layer 5 Manager) 與 SystemController (Layer 6 Integration)。
    ScheduleService 透過此協定啟停排程模式，而無需直接依賴 Integration 層。
    """

    async def activate_schedule_mode(self, strategy: Strategy, *, description: str = "") -> None:
        """
        啟用排程模式

        註冊或更新 ``__schedule__`` 策略並設為 base mode。
        首次呼叫時自動註冊模式；後續呼叫更新策略，觸發 on_strategy_change。

        Args:
            strategy: 排程策略實例
            description: 模式描述（審計用，通常為規則名稱）
        """
        ...

    async def deactivate_schedule_mode(self) -> None:
        """
        停用排程模式

        從 base mode 移除 ``__schedule__``，系統回退到其他 base mode（如果有）。
        """
        ...


__all__ = [
    "ScheduleModeController",
]
