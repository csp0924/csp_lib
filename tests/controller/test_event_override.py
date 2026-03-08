"""Tests for EventDrivenOverride protocol and implementations."""

import pytest

from csp_lib.controller.core import Command, ExecutionConfig, ExecutionMode, Strategy, StrategyContext
from csp_lib.controller.system.event_override import AlarmStopOverride, ContextKeyOverride, EventDrivenOverride
from csp_lib.controller.system.mode import ModeManager, ModePriority, SwitchSource

# ---- Helpers ----


class MockStrategy(Strategy):
    def __init__(self, name: str = "mock"):
        self._name = name

    @property
    def execution_config(self) -> ExecutionConfig:
        return ExecutionConfig(mode=ExecutionMode.PERIODIC, interval_seconds=1)

    def execute(self, context: StrategyContext) -> Command:
        return Command()

    def __repr__(self) -> str:
        return f"MockStrategy({self._name})"


def _make_context(**extra: object) -> StrategyContext:
    """Create a StrategyContext with given extra keys."""
    return StrategyContext(extra=dict(extra))


# ---- EventDrivenOverride Protocol ----


class TestEventDrivenOverrideProtocol:
    def test_alarm_stop_override_implements_protocol(self):
        override = AlarmStopOverride()
        assert isinstance(override, EventDrivenOverride)

    def test_context_key_override_implements_protocol(self):
        override = ContextKeyOverride(
            name="test",
            context_key="key",
            activate_when=lambda v: v is True,
        )
        assert isinstance(override, EventDrivenOverride)

    def test_arbitrary_class_not_protocol(self):
        """A plain object should not satisfy the protocol."""

        class NotAnOverride:
            pass

        assert not isinstance(NotAnOverride(), EventDrivenOverride)


# ---- AlarmStopOverride ----


class TestAlarmStopOverride:
    def test_should_activate_true_when_alarm(self):
        override = AlarmStopOverride()
        ctx = _make_context(system_alarm=True)
        assert override.should_activate(ctx) is True

    def test_should_activate_false_when_no_alarm(self):
        override = AlarmStopOverride()
        ctx = _make_context(system_alarm=False)
        assert override.should_activate(ctx) is False

    def test_should_activate_false_when_key_missing(self):
        override = AlarmStopOverride()
        ctx = _make_context()
        assert override.should_activate(ctx) is False

    def test_custom_alarm_key(self):
        override = AlarmStopOverride(alarm_key="custom_alarm")
        ctx = _make_context(custom_alarm=True)
        assert override.should_activate(ctx) is True

    def test_custom_alarm_key_default_key_ignored(self):
        override = AlarmStopOverride(alarm_key="custom_alarm")
        ctx = _make_context(system_alarm=True)
        assert override.should_activate(ctx) is False

    def test_name_property(self):
        override = AlarmStopOverride()
        assert override.name == "__auto_stop__"

    def test_custom_name(self):
        override = AlarmStopOverride(name="my_stop")
        assert override.name == "my_stop"

    def test_cooldown_seconds_zero(self):
        override = AlarmStopOverride()
        assert override.cooldown_seconds == 0.0

    def test_should_activate_non_bool_truthy_value(self):
        """Only exactly True should activate, not truthy values like 1 or 'yes'."""
        override = AlarmStopOverride()
        ctx_int = _make_context(system_alarm=1)
        ctx_str = _make_context(system_alarm="yes")
        # `1 is True` is False in Python, `"yes" is True` is False
        assert override.should_activate(ctx_int) is False
        assert override.should_activate(ctx_str) is False


# ---- ContextKeyOverride ----


class TestContextKeyOverride:
    def test_should_activate_with_lambda_true(self):
        override = ContextKeyOverride(
            name="islanding",
            context_key="acb_tripped",
            activate_when=lambda v: v is True,
        )
        ctx = _make_context(acb_tripped=True)
        assert override.should_activate(ctx) is True

    def test_should_activate_with_lambda_false(self):
        override = ContextKeyOverride(
            name="islanding",
            context_key="acb_tripped",
            activate_when=lambda v: v is True,
        )
        ctx = _make_context(acb_tripped=False)
        assert override.should_activate(ctx) is False

    def test_should_activate_false_when_key_missing(self):
        override = ContextKeyOverride(
            name="islanding",
            context_key="acb_tripped",
            activate_when=lambda v: v is True,
        )
        ctx = _make_context()
        assert override.should_activate(ctx) is False

    def test_name_property(self):
        override = ContextKeyOverride(
            name="fp_mode",
            context_key="freq_deviation",
            activate_when=lambda v: abs(v) > 0.5,
        )
        assert override.name == "fp_mode"

    def test_default_cooldown_seconds(self):
        override = ContextKeyOverride(
            name="test",
            context_key="key",
            activate_when=lambda v: True,
        )
        assert override.cooldown_seconds == 5.0

    def test_custom_cooldown_seconds(self):
        override = ContextKeyOverride(
            name="test",
            context_key="key",
            activate_when=lambda v: True,
            cooldown_seconds=10.0,
        )
        assert override.cooldown_seconds == 10.0

    def test_zero_cooldown_seconds(self):
        override = ContextKeyOverride(
            name="test",
            context_key="key",
            activate_when=lambda v: True,
            cooldown_seconds=0.0,
        )
        assert override.cooldown_seconds == 0.0

    def test_activate_when_numeric_threshold(self):
        """activate_when with numeric comparison."""
        override = ContextKeyOverride(
            name="fp_mode",
            context_key="freq_deviation",
            activate_when=lambda v: abs(v) > 0.5,
        )
        ctx_high = _make_context(freq_deviation=0.8)
        ctx_low = _make_context(freq_deviation=0.1)
        ctx_boundary = _make_context(freq_deviation=0.5)

        assert override.should_activate(ctx_high) is True
        assert override.should_activate(ctx_low) is False
        assert override.should_activate(ctx_boundary) is False

    def test_activate_when_string_match(self):
        """activate_when with string matching."""
        override = ContextKeyOverride(
            name="emergency",
            context_key="signal",
            activate_when=lambda v: v == "EMERGENCY",
        )
        ctx_match = _make_context(signal="EMERGENCY")
        ctx_no_match = _make_context(signal="NORMAL")

        assert override.should_activate(ctx_match) is True
        assert override.should_activate(ctx_no_match) is False

    def test_activate_when_with_none_value_in_extra(self):
        """When the key exists but value is None, should return False (None guard)."""
        override = ContextKeyOverride(
            name="test",
            context_key="key",
            activate_when=lambda v: True,
        )
        ctx = StrategyContext(extra={"key": None})
        assert override.should_activate(ctx) is False


# ---- SwitchSource Enum ----


class TestSwitchSource:
    def test_all_values_exist(self):
        assert SwitchSource.MANUAL.value == "manual"
        assert SwitchSource.SCHEDULE.value == "schedule"
        assert SwitchSource.EVENT.value == "event"
        assert SwitchSource.INTERNAL.value == "internal"

    def test_member_count(self):
        assert len(SwitchSource) == 4

    def test_enum_uniqueness(self):
        values = [s.value for s in SwitchSource]
        assert len(values) == len(set(values))


# ---- ModeManager Source Tracking ----


class TestModeManagerSourceTracking:
    @pytest.mark.asyncio
    async def test_initial_last_switch_source_is_none(self):
        mm = ModeManager()
        assert mm.last_switch_source is None

    @pytest.mark.asyncio
    async def test_push_override_with_source_event(self):
        mm = ModeManager()
        mm.register("stop", MockStrategy(), ModePriority.PROTECTION)
        await mm.push_override("stop", source=SwitchSource.EVENT)
        assert mm.last_switch_source is SwitchSource.EVENT

    @pytest.mark.asyncio
    async def test_set_base_mode_with_source_manual(self):
        mm = ModeManager()
        mm.register("pq", MockStrategy(), ModePriority.SCHEDULE)
        await mm.set_base_mode("pq", source=SwitchSource.MANUAL)
        assert mm.last_switch_source is SwitchSource.MANUAL

    @pytest.mark.asyncio
    async def test_pop_override_with_source(self):
        mm = ModeManager()
        mm.register("stop", MockStrategy(), ModePriority.PROTECTION)
        await mm.push_override("stop", source=SwitchSource.EVENT)
        await mm.pop_override("stop", source=SwitchSource.INTERNAL)
        assert mm.last_switch_source is SwitchSource.INTERNAL

    @pytest.mark.asyncio
    async def test_push_override_without_source_keeps_previous(self):
        mm = ModeManager()
        mm.register("pq", MockStrategy(), ModePriority.SCHEDULE)
        mm.register("stop", MockStrategy(), ModePriority.PROTECTION)
        await mm.set_base_mode("pq", source=SwitchSource.MANUAL)
        await mm.push_override("stop")
        assert mm.last_switch_source is SwitchSource.MANUAL

    @pytest.mark.asyncio
    async def test_set_base_mode_without_source_keeps_none(self):
        mm = ModeManager()
        mm.register("pq", MockStrategy(), ModePriority.SCHEDULE)
        await mm.set_base_mode("pq")
        assert mm.last_switch_source is None

    @pytest.mark.asyncio
    async def test_pop_override_without_source_keeps_previous(self):
        mm = ModeManager()
        mm.register("stop", MockStrategy(), ModePriority.PROTECTION)
        await mm.push_override("stop", source=SwitchSource.SCHEDULE)
        await mm.pop_override("stop")
        assert mm.last_switch_source is SwitchSource.SCHEDULE

    @pytest.mark.asyncio
    async def test_source_tracks_most_recent(self):
        """Multiple operations with different sources; last one wins."""
        mm = ModeManager()
        mm.register("pq", MockStrategy(), ModePriority.SCHEDULE)
        mm.register("stop", MockStrategy(), ModePriority.PROTECTION)

        await mm.set_base_mode("pq", source=SwitchSource.MANUAL)
        assert mm.last_switch_source is SwitchSource.MANUAL

        await mm.push_override("stop", source=SwitchSource.EVENT)
        assert mm.last_switch_source is SwitchSource.EVENT

        await mm.pop_override("stop", source=SwitchSource.SCHEDULE)
        assert mm.last_switch_source is SwitchSource.SCHEDULE
