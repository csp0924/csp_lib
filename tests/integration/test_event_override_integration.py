"""Integration tests for EventDrivenOverride with SystemController."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from csp_lib.controller.core import Command, ExecutionConfig, ExecutionMode, Strategy, StrategyContext
from csp_lib.controller.system import ModePriority
from csp_lib.controller.system.event_override import AlarmStopOverride, ContextKeyOverride
from csp_lib.controller.system.mode import SwitchSource
from csp_lib.integration.registry import DeviceRegistry
from csp_lib.integration.schema import CommandMapping, ContextMapping
from csp_lib.integration.system_controller import SystemController, SystemControllerConfig

# ---- Helpers (same pattern as test_system_controller.py) ----


def _make_device(
    device_id: str,
    values: dict | None = None,
    responsive: bool = True,
    protected: bool = False,
    connected: bool = True,
) -> MagicMock:
    from csp_lib.core.health import HealthReport, HealthStatus

    dev = MagicMock()
    type(dev).device_id = PropertyMock(return_value=device_id)
    type(dev).is_connected = PropertyMock(return_value=connected)
    type(dev).is_responsive = PropertyMock(return_value=responsive)
    type(dev).is_protected = PropertyMock(return_value=protected)
    type(dev).is_healthy = PropertyMock(return_value=connected and responsive and not protected)
    type(dev).latest_values = PropertyMock(return_value=values or {})
    type(dev).active_alarms = PropertyMock(return_value=[])
    dev.write = AsyncMock()
    unsub_fn = MagicMock()
    dev.on = MagicMock(return_value=unsub_fn)

    def _health():
        if connected and responsive and not protected:
            status = HealthStatus.HEALTHY
        elif connected:
            status = HealthStatus.DEGRADED
        else:
            status = HealthStatus.UNHEALTHY
        return HealthReport(
            status=status,
            component=f"device:{device_id}",
            details={"connected": connected, "responsive": responsive, "protected": protected, "active_alarms": 0},
        )

    dev.health = _health
    return dev


class MockStrategy(Strategy):
    def __init__(self, return_command: Command | None = None, mode: ExecutionMode = ExecutionMode.TRIGGERED):
        self._return_command = return_command or Command()
        self._mode = mode
        self.execute_count = 0
        self.activated = False
        self.deactivated = False

    @property
    def execution_config(self) -> ExecutionConfig:
        return ExecutionConfig(mode=self._mode, interval_seconds=1)

    def execute(self, context: StrategyContext) -> Command:
        self.execute_count += 1
        return self._return_command

    async def on_activate(self) -> None:
        self.activated = True

    async def on_deactivate(self) -> None:
        self.deactivated = True


# ---- Registration Tests ----


class TestRegisterEventOverride:
    def test_register_event_override_adds_to_list(self):
        reg = DeviceRegistry()
        config = SystemControllerConfig(auto_stop_on_alarm=False)
        sc = SystemController(reg, config)

        override = ContextKeyOverride(
            name="test_override",
            context_key="test_key",
            activate_when=lambda v: v is True,
        )
        sc.register_mode("test_override", MockStrategy(), ModePriority.MANUAL)
        sc.register_event_override(override)

        assert len(sc.event_overrides) == 1
        assert sc.event_overrides[0].name == "test_override"

    def test_register_multiple_event_overrides(self):
        reg = DeviceRegistry()
        config = SystemControllerConfig(auto_stop_on_alarm=False)
        sc = SystemController(reg, config)

        o1 = ContextKeyOverride(name="o1", context_key="k1", activate_when=lambda v: True)
        o2 = ContextKeyOverride(name="o2", context_key="k2", activate_when=lambda v: True)
        sc.register_mode("o1", MockStrategy(), ModePriority.MANUAL)
        sc.register_mode("o2", MockStrategy(), ModePriority.MANUAL)
        sc.register_event_override(o1)
        sc.register_event_override(o2)

        assert len(sc.event_overrides) == 2

    def test_auto_stop_on_alarm_registers_event_override(self):
        """When auto_stop_on_alarm=True, AlarmStopOverride is auto-registered."""
        reg = DeviceRegistry()
        config = SystemControllerConfig(auto_stop_on_alarm=True)
        sc = SystemController(reg, config)

        assert len(sc.event_overrides) == 1
        assert sc.event_overrides[0].name == "__auto_stop__"
        assert isinstance(sc.event_overrides[0], AlarmStopOverride)


# ---- Auto-Stop via EventDrivenOverride Regression ----


class TestAutoStopViaEventOverride:
    @pytest.mark.asyncio
    async def test_auto_stop_activates_on_alarm(self):
        """Alarm triggers auto-stop override (regression: same behavior as before)."""
        reg = DeviceRegistry()
        dev = _make_device("pcs1", {"soc": 50.0}, protected=True)
        reg.register(dev)

        config = SystemControllerConfig(
            context_mappings=[ContextMapping(point_name="soc", context_field="soc", device_id="pcs1")],
            command_mappings=[CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1")],
            auto_stop_on_alarm=True,
        )
        sc = SystemController(reg, config)
        strategy = MockStrategy(Command(p_target=500.0))
        sc.register_mode("pq", strategy, ModePriority.SCHEDULE)
        await sc.set_base_mode("pq")

        async with asyncio.timeout(5):
            await sc.start()
            sc.trigger()
            await asyncio.sleep(0.1)
            await sc.stop()

        assert "__auto_stop__" in sc.mode_manager.active_override_names
        assert sc.auto_stop_active is True

    @pytest.mark.asyncio
    async def test_auto_stop_recovery_via_event_override(self):
        """Alarm clears -> auto-stop override removed (cooldown=0)."""
        reg = DeviceRegistry()
        dev = _make_device("pcs1", {"soc": 50.0}, protected=True)
        reg.register(dev)

        config = SystemControllerConfig(
            context_mappings=[ContextMapping(point_name="soc", context_field="soc", device_id="pcs1")],
            command_mappings=[CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1")],
            auto_stop_on_alarm=True,
        )
        sc = SystemController(reg, config)
        strategy = MockStrategy(Command(p_target=500.0))
        sc.register_mode("pq", strategy, ModePriority.SCHEDULE)
        await sc.set_base_mode("pq")

        async with asyncio.timeout(5):
            await sc.start()
            sc.trigger()
            await asyncio.sleep(0.1)
            assert "__auto_stop__" in sc.mode_manager.active_override_names

            # Clear alarm
            type(dev).is_protected = PropertyMock(return_value=False)
            # StopStrategy is PERIODIC with 1s interval
            await asyncio.sleep(1.5)

            assert "__auto_stop__" not in sc.mode_manager.active_override_names
            assert sc.auto_stop_active is False
            await sc.stop()

    @pytest.mark.asyncio
    async def test_auto_stop_source_is_event(self):
        """Auto-stop override uses SwitchSource.EVENT."""
        reg = DeviceRegistry()
        dev = _make_device("pcs1", {"soc": 50.0}, protected=True)
        reg.register(dev)

        config = SystemControllerConfig(
            context_mappings=[ContextMapping(point_name="soc", context_field="soc", device_id="pcs1")],
            command_mappings=[CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1")],
            auto_stop_on_alarm=True,
        )
        sc = SystemController(reg, config)
        strategy = MockStrategy(Command(p_target=500.0))
        sc.register_mode("pq", strategy, ModePriority.SCHEDULE)
        await sc.set_base_mode("pq")

        async with asyncio.timeout(5):
            await sc.start()
            sc.trigger()
            await asyncio.sleep(0.1)
            await sc.stop()

        assert sc.mode_manager.last_switch_source is SwitchSource.EVENT


# ---- ContextKeyOverride Integration ----


class TestContextKeyOverrideIntegration:
    @pytest.mark.asyncio
    async def test_context_key_override_triggers_push(self):
        """ContextKeyOverride activates override when condition met."""
        reg = DeviceRegistry()
        dev = _make_device("pcs1", {"soc": 50.0, "acb_status": True})
        reg.register(dev)

        config = SystemControllerConfig(
            context_mappings=[
                ContextMapping(point_name="soc", context_field="soc", device_id="pcs1"),
                ContextMapping(point_name="acb_status", context_field="extra.acb_tripped", device_id="pcs1"),
            ],
            command_mappings=[CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1")],
            auto_stop_on_alarm=False,
        )
        sc = SystemController(reg, config)

        # Register the islanding mode and override
        islanding_strategy = MockStrategy(Command(p_target=0.0))
        sc.register_mode("pq", MockStrategy(Command(p_target=500.0)), ModePriority.SCHEDULE)
        sc.register_mode("islanding", islanding_strategy, ModePriority.PROTECTION)

        override = ContextKeyOverride(
            name="islanding",
            context_key="acb_tripped",
            activate_when=lambda v: v is True,
            cooldown_seconds=0.0,
        )
        sc.register_event_override(override)

        await sc.set_base_mode("pq")

        async with asyncio.timeout(5):
            await sc.start()
            sc.trigger()
            await asyncio.sleep(0.1)
            await sc.stop()

        assert "islanding" in sc.mode_manager.active_override_names
        assert sc.mode_manager.last_switch_source is SwitchSource.EVENT

    @pytest.mark.asyncio
    async def test_context_key_override_pops_when_condition_clears(self):
        """ContextKeyOverride deactivates when condition no longer met (cooldown=0)."""
        reg = DeviceRegistry()
        dev = _make_device("pcs1", {"soc": 50.0, "acb_status": True})
        reg.register(dev)

        config = SystemControllerConfig(
            context_mappings=[
                ContextMapping(point_name="soc", context_field="soc", device_id="pcs1"),
                ContextMapping(point_name="acb_status", context_field="extra.acb_tripped", device_id="pcs1"),
            ],
            command_mappings=[CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1")],
            auto_stop_on_alarm=False,
        )
        sc = SystemController(reg, config)

        sc.register_mode("pq", MockStrategy(Command(p_target=500.0)), ModePriority.SCHEDULE)
        islanding_strategy = MockStrategy(Command(p_target=0.0), mode=ExecutionMode.PERIODIC)
        sc.register_mode("islanding", islanding_strategy, ModePriority.PROTECTION)

        override = ContextKeyOverride(
            name="islanding",
            context_key="acb_tripped",
            activate_when=lambda v: v is True,
            cooldown_seconds=0.0,
        )
        sc.register_event_override(override)

        await sc.set_base_mode("pq")

        async with asyncio.timeout(5):
            await sc.start()
            sc.trigger()
            await asyncio.sleep(0.1)
            assert "islanding" in sc.mode_manager.active_override_names

            # Clear condition
            type(dev).latest_values = PropertyMock(return_value={"soc": 50.0, "acb_status": False})
            # Wait for periodic cycle of the override strategy
            await asyncio.sleep(1.5)

            assert "islanding" not in sc.mode_manager.active_override_names
            await sc.stop()


# ---- Cooldown Mechanism ----


class TestCooldownMechanism:
    @pytest.mark.asyncio
    async def test_cooldown_prevents_immediate_deactivation(self):
        """Override should remain active during cooldown even after condition clears."""
        reg = DeviceRegistry()
        dev = _make_device("pcs1", {"soc": 50.0, "signal": "ON"})
        reg.register(dev)

        config = SystemControllerConfig(
            context_mappings=[
                ContextMapping(point_name="signal", context_field="extra.signal", device_id="pcs1"),
            ],
            command_mappings=[CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1")],
            auto_stop_on_alarm=False,
        )
        sc = SystemController(reg, config)

        sc.register_mode("pq", MockStrategy(Command(p_target=500.0)), ModePriority.SCHEDULE)
        sc.register_mode(
            "special", MockStrategy(Command(p_target=0.0), mode=ExecutionMode.PERIODIC), ModePriority.PROTECTION
        )

        override = ContextKeyOverride(
            name="special",
            context_key="signal",
            activate_when=lambda v: v == "ON",
            cooldown_seconds=3.0,
        )
        sc.register_event_override(override)
        await sc.set_base_mode("pq")

        async with asyncio.timeout(10):
            await sc.start()
            sc.trigger()
            await asyncio.sleep(0.1)
            assert "special" in sc.mode_manager.active_override_names

            # Clear condition
            type(dev).latest_values = PropertyMock(return_value={"soc": 50.0, "signal": "OFF"})
            # Wait a bit, but less than cooldown
            await asyncio.sleep(1.5)

            # Should still be active due to cooldown (3s > 1.5s elapsed)
            assert "special" in sc.mode_manager.active_override_names

            await sc.stop()


# ---- Multiple Event Overrides Coexistence ----


class TestMultipleEventOverrides:
    @pytest.mark.asyncio
    async def test_multiple_overrides_can_coexist(self):
        """Two event overrides can both activate independently."""
        reg = DeviceRegistry()
        dev = _make_device("pcs1", {"soc": 50.0, "acb_tripped": True, "freq_high": True}, protected=True)
        reg.register(dev)

        config = SystemControllerConfig(
            context_mappings=[
                ContextMapping(point_name="acb_tripped", context_field="extra.acb_tripped", device_id="pcs1"),
                ContextMapping(point_name="freq_high", context_field="extra.freq_high", device_id="pcs1"),
            ],
            command_mappings=[CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1")],
            auto_stop_on_alarm=True,
        )
        sc = SystemController(reg, config)

        # auto_stop is already registered by config
        # Register additional overrides
        sc.register_mode("islanding", MockStrategy(Command(p_target=0.0)), ModePriority.MANUAL)
        sc.register_mode("fp_mode", MockStrategy(Command(p_target=-100.0)), ModePriority.SCHEDULE)

        o1 = ContextKeyOverride(
            name="islanding",
            context_key="acb_tripped",
            activate_when=lambda v: v is True,
            cooldown_seconds=0.0,
        )
        o2 = ContextKeyOverride(
            name="fp_mode",
            context_key="freq_high",
            activate_when=lambda v: v is True,
            cooldown_seconds=0.0,
        )
        sc.register_event_override(o1)
        sc.register_event_override(o2)

        sc.register_mode("pq", MockStrategy(Command(p_target=500.0)), ModePriority.SCHEDULE)
        await sc.set_base_mode("pq")

        async with asyncio.timeout(5):
            await sc.start()
            sc.trigger()
            await asyncio.sleep(0.1)
            await sc.stop()

        active = sc.mode_manager.active_override_names
        # All three overrides should be active
        assert "__auto_stop__" in active
        assert "islanding" in active
        assert "fp_mode" in active

    def test_event_overrides_list_independent_of_auto_stop(self):
        """event_overrides property returns copies, not references."""
        reg = DeviceRegistry()
        config = SystemControllerConfig(auto_stop_on_alarm=True)
        sc = SystemController(reg, config)

        overrides = sc.event_overrides
        assert len(overrides) == 1
        # Modifying the returned list should not affect internal state
        overrides.clear()
        assert len(sc.event_overrides) == 1


# ---- _evaluate_event_overrides edge cases ----


class TestEvaluateEventOverridesEdgeCases:
    @pytest.mark.asyncio
    async def test_push_override_already_active_is_silently_ignored(self):
        """If push_override raises ValueError (already active), it is caught."""
        reg = DeviceRegistry()
        dev = _make_device("pcs1", {"soc": 50.0}, protected=True)
        reg.register(dev)

        config = SystemControllerConfig(
            context_mappings=[ContextMapping(point_name="soc", context_field="soc", device_id="pcs1")],
            command_mappings=[CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1")],
            auto_stop_on_alarm=True,
        )
        sc = SystemController(reg, config)
        strategy = MockStrategy(Command(p_target=500.0))
        sc.register_mode("pq", strategy, ModePriority.SCHEDULE)
        await sc.set_base_mode("pq")

        # Run twice to verify no errors from duplicate activation
        async with asyncio.timeout(5):
            await sc.start()
            sc.trigger()
            await asyncio.sleep(0.1)
            sc.trigger()
            await asyncio.sleep(0.1)
            await sc.stop()

        assert "__auto_stop__" in sc.mode_manager.active_override_names
