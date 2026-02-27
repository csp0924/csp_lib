# =============== SubExecutorAgent Protocol ===============
#
# 遠端子執行器代理協定
#
# 定義 SCADA/Area 層對下級 Site/Device 層的統一操控介面：
#   - dispatch: 下發調度命令
#   - get_status: 查詢子執行器狀態
#   - push_override / pop_override: 遠端模式覆蓋
#   - health_check: 健康檢查
#
# 放置於 Layer 6 (Integration)，依賴 Layer 4 (Controller) 的
# Command / StrategyContext / Strategy，由 Layer 7/8 提供具體實作。

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from .status import ExecutorStatus
    from .transport import DispatchCommand


@runtime_checkable
class SubExecutorAgent(Protocol):
    """
    遠端子執行器代理協定

    抽象化對遠端 Site 級控制器的操控，使上層編排器
    （SCADA / Area controller）可透過統一介面協調多站點。

    設計考量：
    - 所有方法皆為 async，支援遠端通訊延遲
    - dispatch() 為單向下發，不等待執行結果
    - get_status() 為查詢式，回傳最新快取狀態
    - 實作方應確保 health_check() 為輕量操作

    Usage::

        agent: SubExecutorAgent = RedisSubExecutorAgent(site_id="site_bms", ...)

        # 下發命令
        cmd = DispatchCommand(
            source_site_id="scada",
            target_site_id="site_bms",
            command=Command(p_target=500.0, q_target=100.0),
        )
        await agent.dispatch(cmd)

        # 查詢狀態
        status = await agent.get_status()
        print(status.strategy_name, status.last_command)
    """

    @property
    def site_id(self) -> str:
        """子執行器所屬站點 ID"""
        ...

    async def dispatch(self, command: DispatchCommand) -> None:
        """
        下發調度命令給子執行器

        Args:
            command: 調度命令，包含來源、目標、Command 與優先序
        """
        ...

    async def get_status(self) -> ExecutorStatus:
        """
        查詢子執行器當前狀態

        Returns:
            ExecutorStatus: 包含策略名稱、活躍覆蓋、最新命令等資訊
        """
        ...

    async def push_override(self, mode_name: str) -> None:
        """
        遠端推入覆蓋模式

        對應 ModeManager.push_override()，由上層調度器觸發。

        Args:
            mode_name: 已在子執行器註冊的模式名稱
        """
        ...

    async def pop_override(self, mode_name: str) -> None:
        """
        遠端移除覆蓋模式

        對應 ModeManager.pop_override()，由上層調度器觸發。

        Args:
            mode_name: 要移除的覆蓋模式名稱
        """
        ...

    async def health_check(self) -> bool:
        """
        健康檢查

        Returns:
            True 表示子執行器可達且正常運作
        """
        ...


__all__ = [
    "SubExecutorAgent",
]
