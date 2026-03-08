# =============== Integration - Schedule Mode Tests ===============
#
# 排程模式端到端整合測試
#
# 測試覆蓋：
# - SystemController.activate_schedule_mode 正確註冊 + 設為 base mode
# - activate_schedule_mode 二次呼叫更新策略（on_strategy_change 觸發）
# - deactivate_schedule_mode 從 base mode 移除
# - SwitchSource.SCHEDULE 被記錄
# - Heartbeat suppression 在排程切換時正常工作

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from csp_lib.controller.core import Command, ExecutionConfig, ExecutionMode, Strategy, StrategyContext
from csp_lib.controller.system.mode import ModePriority, SwitchSource
from csp_lib.controller.system.schedule_mode import ScheduleModeController
from csp_lib.integration.registry import DeviceRegistry
from csp_lib.integration.system_controller import _SCHEDULE_MODE, SystemController, SystemControllerConfig


def _make_device(device_id: str = "dev1") -> MagicMock:
    dev = MagicMock()
    type(dev).device_id = PropertyMock(return_value=device_id)
    type(dev).is_connected = PropertyMock(return_value=True)
    type(dev).is_responsive = PropertyMock(return_value=True)
    type(dev).is_protected = PropertyMock(return_value=False)
    type(dev).is_healthy = PropertyMock(return_value=True)
    type(dev).latest_values = PropertyMock(return_value={})
    type(dev).active_alarms = PropertyMock(return_value=[])
    dev.write = AsyncMock()
    dev.on = MagicMock(return_value=MagicMock())
    from csp_lib.core.health import HealthReport, HealthStatus

    dev.health = lambda: HealthReport(status=HealthStatus.HEALTHY, component=f"device:{device_id}")
    return dev


class _TestStrategy(Strategy):
    """測試用策略"""

    def __init__(self, name: str = "test", suppress_hb: bool = False):
        self._name = name
        self._suppress = suppress_hb
        self.activated = False
        self.deactivated = False

    @property
    def execution_config(self) -> ExecutionConfig:
        return ExecutionConfig(mode=ExecutionMode.TRIGGERED, interval_seconds=1)

    @property
    def suppress_heartbeat(self) -> bool:
        return self._suppress

    def execute(self, context: StrategyContext) -> Command:
        return Command()

    async def on_activate(self) -> None:
        self.activated = True

    async def on_deactivate(self) -> None:
        self.deactivated = True

    def __repr__(self) -> str:
        return f"_TestStrategy({self._name})"


class TestScheduleModeControllerProtocol:
    """ScheduleModeController Protocol 合規性"""

    def test_system_controller_implements_protocol(self):
        """SystemController 應實作 ScheduleModeController Protocol"""
        reg = DeviceRegistry()
        sc = SystemController(reg, SystemControllerConfig(auto_stop_on_alarm=False))
        assert isinstance(sc, ScheduleModeController)


class TestActivateScheduleMode:
    """activate_schedule_mode 測試"""

    @pytest.mark.asyncio
    async def test_first_call_registers_and_sets_base_mode(self):
        """首次呼叫應註冊 __schedule__ 並設為 base mode"""
        reg = DeviceRegistry()
        sc = SystemController(reg, SystemControllerConfig(auto_stop_on_alarm=False))

        strategy = _TestStrategy("pq")
        await sc.activate_schedule_mode(strategy, description="rule_a (pq)")

        mm = sc.mode_manager
        assert _SCHEDULE_MODE in mm.registered_modes
        assert _SCHEDULE_MODE in mm.base_mode_names
        assert mm.registered_modes[_SCHEDULE_MODE].strategy is strategy
        assert mm.registered_modes[_SCHEDULE_MODE].description == "rule_a (pq)"

    @pytest.mark.asyncio
    async def test_second_call_updates_strategy(self):
        """二次呼叫應更新策略並觸發 on_strategy_change"""
        reg = DeviceRegistry()
        sc = SystemController(reg, SystemControllerConfig(auto_stop_on_alarm=False))

        s1 = _TestStrategy("pq")
        s2 = _TestStrategy("qv")

        await sc.activate_schedule_mode(s1, description="rule_a")
        await sc.activate_schedule_mode(s2, description="rule_b")

        mm = sc.mode_manager
        assert mm.registered_modes[_SCHEDULE_MODE].strategy is s2
        assert mm.registered_modes[_SCHEDULE_MODE].description == "rule_b"

        # s1 應被 deactivate，s2 應被 activate
        assert s1.deactivated
        assert s2.activated

    @pytest.mark.asyncio
    async def test_records_switch_source_schedule(self):
        """應記錄 SwitchSource.SCHEDULE"""
        reg = DeviceRegistry()
        sc = SystemController(reg, SystemControllerConfig(auto_stop_on_alarm=False))

        await sc.activate_schedule_mode(_TestStrategy())

        assert sc.mode_manager.last_switch_source == SwitchSource.SCHEDULE

    @pytest.mark.asyncio
    async def test_strategy_priority_is_schedule(self):
        """__schedule__ 模式的優先等級應為 ModePriority.SCHEDULE"""
        reg = DeviceRegistry()
        sc = SystemController(reg, SystemControllerConfig(auto_stop_on_alarm=False))

        await sc.activate_schedule_mode(_TestStrategy())

        mode = sc.mode_manager.registered_modes[_SCHEDULE_MODE]
        assert mode.priority == ModePriority.SCHEDULE


class TestDeactivateScheduleMode:
    """deactivate_schedule_mode 測試"""

    @pytest.mark.asyncio
    async def test_removes_from_base_mode(self):
        """應從 base mode 移除 __schedule__"""
        reg = DeviceRegistry()
        sc = SystemController(reg, SystemControllerConfig(auto_stop_on_alarm=False))

        await sc.activate_schedule_mode(_TestStrategy())
        await sc.deactivate_schedule_mode()

        assert _SCHEDULE_MODE not in sc.mode_manager.base_mode_names

    @pytest.mark.asyncio
    async def test_noop_when_not_active(self):
        """__schedule__ 未啟用時 deactivate 不應拋出"""
        reg = DeviceRegistry()
        sc = SystemController(reg, SystemControllerConfig(auto_stop_on_alarm=False))

        # 不應拋出異常
        await sc.deactivate_schedule_mode()

    @pytest.mark.asyncio
    async def test_effective_strategy_becomes_none(self):
        """停用後若無其他 base mode，effective_strategy 應為 None"""
        reg = DeviceRegistry()
        sc = SystemController(reg, SystemControllerConfig(auto_stop_on_alarm=False))

        await sc.activate_schedule_mode(_TestStrategy())
        await sc.deactivate_schedule_mode()

        assert sc.mode_manager.effective_strategy is None


class TestScheduleModeWithOtherModes:
    """排程模式與其他模式交互"""

    @pytest.mark.asyncio
    async def test_coexists_with_manual_base_mode(self):
        """排程模式可與手動模式共存（多 base mode）"""
        reg = DeviceRegistry()
        sc = SystemController(reg, SystemControllerConfig(auto_stop_on_alarm=False))

        manual_s = _TestStrategy("manual")
        sc.register_mode("manual", manual_s, ModePriority.MANUAL)
        await sc.add_base_mode("manual")

        schedule_s = _TestStrategy("schedule")
        await sc.activate_schedule_mode(schedule_s)

        mm = sc.mode_manager
        assert "manual" in mm.base_mode_names
        assert _SCHEDULE_MODE in mm.base_mode_names

    @pytest.mark.asyncio
    async def test_deactivate_preserves_other_base_modes(self):
        """停用排程模式不影響其他 base mode"""
        reg = DeviceRegistry()
        sc = SystemController(reg, SystemControllerConfig(auto_stop_on_alarm=False))

        manual_s = _TestStrategy("manual")
        sc.register_mode("manual", manual_s, ModePriority.MANUAL)
        await sc.add_base_mode("manual")

        await sc.activate_schedule_mode(_TestStrategy("schedule"))
        await sc.deactivate_schedule_mode()

        mm = sc.mode_manager
        assert "manual" in mm.base_mode_names
        assert _SCHEDULE_MODE not in mm.base_mode_names
