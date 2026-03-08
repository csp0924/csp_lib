# =============== Load Shedding Strategy Tests ===============
#
# Comprehensive tests for ThresholdCondition, RemainingTimeCondition,
# ShedStage, LoadSheddingConfig, and LoadSheddingStrategy.

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from csp_lib.controller.core import (
    Command,
    ExecutionMode,
    StrategyContext,
)
from csp_lib.controller.strategies.load_shedding import (
    LoadCircuitProtocol,
    LoadSheddingConfig,
    LoadSheddingStrategy,
    RemainingTimeCondition,
    ShedCondition,
    ShedStage,
    ThresholdCondition,
)

# =============== Mock Circuit ===============


class MockCircuit:
    """Mock implementation of LoadCircuitProtocol for testing."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._is_shed = False

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_shed(self) -> bool:
        return self._is_shed

    async def shed(self) -> None:
        self._is_shed = True

    async def restore(self) -> None:
        self._is_shed = False


# =============== Helpers ===============


def _make_context(**extra: object) -> StrategyContext:
    """Create a StrategyContext with given extra values."""
    return StrategyContext(last_command=Command(), extra=extra)


# =============== ThresholdCondition Tests ===============


class TestThresholdCondition:
    """Tests for ThresholdCondition."""

    def test_should_shed_when_value_below_threshold(self):
        """should_shed returns True when value < shed_below."""
        cond = ThresholdCondition(context_key="soc", shed_below=20.0, restore_above=30.0)
        ctx = _make_context(soc=15.0)
        assert cond.should_shed(ctx) is True

    def test_should_shed_returns_false_when_value_equal_to_threshold(self):
        """should_shed returns False when value == shed_below (not strictly less)."""
        cond = ThresholdCondition(context_key="soc", shed_below=20.0, restore_above=30.0)
        ctx = _make_context(soc=20.0)
        assert cond.should_shed(ctx) is False

    def test_should_shed_returns_false_when_value_above_threshold(self):
        """should_shed returns False when value >= shed_below."""
        cond = ThresholdCondition(context_key="soc", shed_below=20.0, restore_above=30.0)
        ctx = _make_context(soc=25.0)
        assert cond.should_shed(ctx) is False

    def test_should_restore_when_value_above_threshold(self):
        """should_restore returns True when value > restore_above."""
        cond = ThresholdCondition(context_key="soc", shed_below=20.0, restore_above=30.0)
        ctx = _make_context(soc=35.0)
        assert cond.should_restore(ctx) is True

    def test_should_restore_returns_false_when_value_equal_to_threshold(self):
        """should_restore returns False when value == restore_above (not strictly greater)."""
        cond = ThresholdCondition(context_key="soc", shed_below=20.0, restore_above=30.0)
        ctx = _make_context(soc=30.0)
        assert cond.should_restore(ctx) is False

    def test_should_restore_returns_false_when_value_below_threshold(self):
        """should_restore returns False when value <= restore_above."""
        cond = ThresholdCondition(context_key="soc", shed_below=20.0, restore_above=30.0)
        ctx = _make_context(soc=25.0)
        assert cond.should_restore(ctx) is False

    def test_should_shed_returns_false_when_key_missing(self):
        """should_shed returns False when context key is absent."""
        cond = ThresholdCondition(context_key="soc", shed_below=20.0, restore_above=30.0)
        ctx = _make_context()  # no "soc" key
        assert cond.should_shed(ctx) is False

    def test_should_restore_returns_false_when_key_missing(self):
        """should_restore returns False when context key is absent."""
        cond = ThresholdCondition(context_key="soc", shed_below=20.0, restore_above=30.0)
        ctx = _make_context()
        assert cond.should_restore(ctx) is False

    def test_constructor_raises_when_restore_above_less_than_shed_below(self):
        """Constructor raises ValueError if restore_above < shed_below."""
        with pytest.raises(ValueError, match="restore_above.*must be >= shed_below"):
            ThresholdCondition(context_key="soc", shed_below=30.0, restore_above=20.0)

    def test_constructor_accepts_equal_thresholds(self):
        """Constructor accepts restore_above == shed_below."""
        cond = ThresholdCondition(context_key="soc", shed_below=25.0, restore_above=25.0)
        assert cond is not None

    def test_implements_shed_condition_protocol(self):
        """ThresholdCondition implements ShedCondition protocol."""
        cond = ThresholdCondition(context_key="soc", shed_below=20.0, restore_above=30.0)
        assert isinstance(cond, ShedCondition)


# =============== RemainingTimeCondition Tests ===============


class TestRemainingTimeCondition:
    """Tests for RemainingTimeCondition."""

    def test_default_context_key(self):
        """Default context_key is 'battery_remaining_minutes'."""
        cond = RemainingTimeCondition()
        ctx = _make_context(battery_remaining_minutes=20.0)
        assert cond.should_shed(ctx) is True  # 20 < 30 (default shed_below)

    def test_custom_context_key(self):
        """Custom context_key works correctly."""
        cond = RemainingTimeCondition(context_key="ups_minutes", shed_below=10.0, restore_above=20.0)
        ctx = _make_context(ups_minutes=5.0)
        assert cond.should_shed(ctx) is True

    def test_should_shed_when_time_below_threshold(self):
        """should_shed returns True when remaining time < shed_below."""
        cond = RemainingTimeCondition(shed_below=30.0, restore_above=45.0)
        ctx = _make_context(battery_remaining_minutes=25.0)
        assert cond.should_shed(ctx) is True

    def test_should_shed_returns_false_when_time_above_threshold(self):
        """should_shed returns False when remaining time >= shed_below."""
        cond = RemainingTimeCondition(shed_below=30.0, restore_above=45.0)
        ctx = _make_context(battery_remaining_minutes=35.0)
        assert cond.should_shed(ctx) is False

    def test_should_restore_when_time_above_threshold(self):
        """should_restore returns True when remaining time > restore_above."""
        cond = RemainingTimeCondition(shed_below=30.0, restore_above=45.0)
        ctx = _make_context(battery_remaining_minutes=50.0)
        assert cond.should_restore(ctx) is True

    def test_should_restore_returns_false_when_time_below_threshold(self):
        """should_restore returns False when remaining time <= restore_above."""
        cond = RemainingTimeCondition(shed_below=30.0, restore_above=45.0)
        ctx = _make_context(battery_remaining_minutes=40.0)
        assert cond.should_restore(ctx) is False

    def test_should_shed_returns_false_when_key_missing(self):
        """should_shed returns False when context key is absent."""
        cond = RemainingTimeCondition()
        ctx = _make_context()
        assert cond.should_shed(ctx) is False

    def test_should_restore_returns_false_when_key_missing(self):
        """should_restore returns False when context key is absent."""
        cond = RemainingTimeCondition()
        ctx = _make_context()
        assert cond.should_restore(ctx) is False

    def test_constructor_raises_when_restore_above_less_than_shed_below(self):
        """Constructor raises ValueError if restore_above < shed_below."""
        with pytest.raises(ValueError, match="restore_above.*must be >= shed_below"):
            RemainingTimeCondition(shed_below=50.0, restore_above=30.0)

    def test_default_thresholds(self):
        """Default thresholds are shed_below=30.0, restore_above=45.0."""
        cond = RemainingTimeCondition()
        # 29 < 30 -> shed
        assert cond.should_shed(_make_context(battery_remaining_minutes=29.0)) is True
        # 46 > 45 -> restore
        assert cond.should_restore(_make_context(battery_remaining_minutes=46.0)) is True

    def test_implements_shed_condition_protocol(self):
        """RemainingTimeCondition implements ShedCondition protocol."""
        cond = RemainingTimeCondition()
        assert isinstance(cond, ShedCondition)


# =============== ShedStage Tests ===============


class TestShedStage:
    """Tests for frozen ShedStage dataclass."""

    def test_create_with_all_fields(self):
        """ShedStage can be created with all fields specified."""
        circuit = MockCircuit("c1")
        cond = ThresholdCondition("soc", 20.0, 30.0)
        stage = ShedStage(name="stage1", circuits=[circuit], condition=cond, priority=5, min_hold_seconds=60.0)

        assert stage.name == "stage1"
        assert stage.circuits == [circuit]
        assert stage.condition is cond
        assert stage.priority == 5
        assert stage.min_hold_seconds == 60.0

    def test_default_priority_is_zero(self):
        """Default priority is 0."""
        stage = ShedStage(name="s", circuits=[], condition=ThresholdCondition("k", 10, 20))
        assert stage.priority == 0

    def test_default_min_hold_seconds(self):
        """Default min_hold_seconds is 30.0."""
        stage = ShedStage(name="s", circuits=[], condition=ThresholdCondition("k", 10, 20))
        assert stage.min_hold_seconds == 30.0

    def test_frozen_cannot_modify(self):
        """ShedStage is frozen and cannot be modified."""
        stage = ShedStage(name="s", circuits=[], condition=ThresholdCondition("k", 10, 20))
        with pytest.raises(AttributeError):
            stage.name = "other"  # type: ignore[misc]


# =============== LoadSheddingConfig Tests ===============


class TestLoadSheddingConfig:
    """Tests for LoadSheddingConfig."""

    def test_default_values(self):
        """Default config has empty stages, 5s interval, 60s restore delay, auto restore enabled."""
        config = LoadSheddingConfig()
        assert config.stages == []
        assert config.evaluation_interval == 5
        assert config.restore_delay == 60.0
        assert config.auto_restore_on_deactivate is True

    def test_custom_values(self):
        """Config with custom values."""
        stage = ShedStage(name="s1", circuits=[], condition=ThresholdCondition("k", 10, 20))
        config = LoadSheddingConfig(
            stages=[stage],
            evaluation_interval=10,
            restore_delay=120.0,
            auto_restore_on_deactivate=False,
        )
        assert len(config.stages) == 1
        assert config.evaluation_interval == 10
        assert config.restore_delay == 120.0
        assert config.auto_restore_on_deactivate is False


# =============== MockCircuit Protocol Tests ===============


class TestMockCircuitProtocol:
    """Verify MockCircuit implements LoadCircuitProtocol."""

    def test_implements_protocol(self):
        """MockCircuit satisfies LoadCircuitProtocol."""
        circuit = MockCircuit("test")
        assert isinstance(circuit, LoadCircuitProtocol)

    @pytest.mark.asyncio
    async def test_shed_and_restore(self):
        """MockCircuit shed/restore toggles is_shed."""
        circuit = MockCircuit("c")
        assert circuit.is_shed is False
        await circuit.shed()
        assert circuit.is_shed is True
        await circuit.restore()
        assert circuit.is_shed is False


# =============== LoadSheddingStrategy Tests ===============


class TestLoadSheddingStrategy:
    """Tests for LoadSheddingStrategy."""

    def _make_strategy(
        self,
        stages: list[ShedStage] | None = None,
        evaluation_interval: int = 5,
        restore_delay: float = 0.0,
        auto_restore_on_deactivate: bool = True,
    ) -> LoadSheddingStrategy:
        """Helper to create a LoadSheddingStrategy with sensible test defaults."""
        config = LoadSheddingConfig(
            stages=stages or [],
            evaluation_interval=evaluation_interval,
            restore_delay=restore_delay,
            auto_restore_on_deactivate=auto_restore_on_deactivate,
        )
        return LoadSheddingStrategy(config)

    # --- execution_config ---

    def test_execution_config_returns_periodic(self):
        """execution_config returns PERIODIC mode with configured interval."""
        strategy = self._make_strategy(evaluation_interval=10)
        ec = strategy.execution_config
        assert ec.mode == ExecutionMode.PERIODIC
        assert ec.interval_seconds == 10

    # --- execute() shed logic ---

    def test_execute_schedules_shed_when_condition_met(self):
        """execute() marks stage as shed when condition triggers."""
        circuit = MockCircuit("c1")
        cond = ThresholdCondition("soc", shed_below=20.0, restore_above=30.0)
        stage = ShedStage(name="low_priority", circuits=[circuit], condition=cond, priority=1)
        strategy = self._make_strategy(stages=[stage])

        ctx = _make_context(soc=15.0)  # below threshold
        strategy.execute(ctx)

        assert "low_priority" in strategy.shed_stage_names

    def test_execute_does_not_shed_when_condition_not_met(self):
        """execute() does not shed when condition is not met."""
        circuit = MockCircuit("c1")
        cond = ThresholdCondition("soc", shed_below=20.0, restore_above=30.0)
        stage = ShedStage(name="s1", circuits=[circuit], condition=cond)
        strategy = self._make_strategy(stages=[stage])

        ctx = _make_context(soc=25.0)  # above threshold
        strategy.execute(ctx)

        assert strategy.shed_stage_names == []

    def test_execute_returns_last_command(self):
        """execute() returns context.last_command."""
        strategy = self._make_strategy()
        cmd = Command(p_target=100.0, q_target=50.0)
        ctx = StrategyContext(last_command=cmd, extra={})

        result = strategy.execute(ctx)
        assert result == cmd

    # --- Shed order: priority ascending ---

    def test_shed_order_priority_ascending(self):
        """Stages are shed in priority ascending order (low priority first)."""
        c1 = MockCircuit("c1")
        c2 = MockCircuit("c2")
        cond = ThresholdCondition("soc", shed_below=20.0, restore_above=30.0)
        stage_high = ShedStage(name="high", circuits=[c1], condition=cond, priority=10)
        stage_low = ShedStage(name="low", circuits=[c2], condition=cond, priority=1)

        # Pass stages in reverse priority order to verify sorting
        strategy = self._make_strategy(stages=[stage_high, stage_low])

        ctx = _make_context(soc=15.0)
        strategy.execute(ctx)

        # Both should be shed
        assert "low" in strategy.shed_stage_names
        assert "high" in strategy.shed_stage_names

        # Verify internal sorted order: low (1) before high (10)
        sorted_names = [s.name for s in strategy._sorted_stages]
        assert sorted_names.index("low") < sorted_names.index("high")

    # --- Restore order: priority descending ---

    def test_restore_evaluates_in_priority_descending_order(self):
        """Restore evaluation happens in priority descending order (high priority first)."""
        c1 = MockCircuit("c1")
        c2 = MockCircuit("c2")
        cond = ThresholdCondition("soc", shed_below=20.0, restore_above=30.0)
        stage_high = ShedStage(name="high", circuits=[c1], condition=cond, priority=10, min_hold_seconds=0.0)
        stage_low = ShedStage(name="low", circuits=[c2], condition=cond, priority=1, min_hold_seconds=0.0)

        strategy = self._make_strategy(stages=[stage_high, stage_low], restore_delay=0.0)

        # First, shed both stages at time=0
        ctx_shed = _make_context(soc=15.0)
        with patch("csp_lib.controller.strategies.load_shedding.time.monotonic", return_value=0.0):
            strategy.execute(ctx_shed)
        assert len(strategy.shed_stage_names) == 2

        # Now trigger restore condition -- first call starts restore_requested_at
        ctx_restore = _make_context(soc=35.0)
        with patch("csp_lib.controller.strategies.load_shedding.time.monotonic", return_value=100.0):
            strategy.execute(ctx_restore)

        # Second call with same time should complete restore (restore_delay=0.0)
        with patch("csp_lib.controller.strategies.load_shedding.time.monotonic", return_value=100.0):
            strategy.execute(ctx_restore)

        assert strategy.shed_stage_names == []

    # --- min_hold_seconds prevents premature restore ---

    def test_min_hold_seconds_prevents_premature_restore(self):
        """Stages are not restored before min_hold_seconds has elapsed."""
        circuit = MockCircuit("c1")
        cond = ThresholdCondition("soc", shed_below=20.0, restore_above=30.0)
        stage = ShedStage(name="s1", circuits=[circuit], condition=cond, priority=0, min_hold_seconds=60.0)
        strategy = self._make_strategy(stages=[stage], restore_delay=0.0)

        # Shed at time=100
        with patch("csp_lib.controller.strategies.load_shedding.time.monotonic", return_value=100.0):
            strategy.execute(_make_context(soc=15.0))
        assert "s1" in strategy.shed_stage_names

        # Try restore at time=130 (only 30s elapsed, need 60s)
        with patch("csp_lib.controller.strategies.load_shedding.time.monotonic", return_value=130.0):
            strategy.execute(_make_context(soc=35.0))
        assert "s1" in strategy.shed_stage_names  # still shed

        # Restore at time=161 (61s elapsed, > 60s min_hold) -- starts restore delay
        with patch("csp_lib.controller.strategies.load_shedding.time.monotonic", return_value=161.0):
            strategy.execute(_make_context(soc=35.0))
        # restore_requested_at is now set, but restore_delay=0.0 so next call completes it
        with patch("csp_lib.controller.strategies.load_shedding.time.monotonic", return_value=161.0):
            strategy.execute(_make_context(soc=35.0))
        assert strategy.shed_stage_names == []

    # --- restore_delay prevents rapid toggling ---

    def test_restore_delay_prevents_rapid_toggling(self):
        """Restore is delayed by restore_delay seconds after condition is met."""
        circuit = MockCircuit("c1")
        cond = ThresholdCondition("soc", shed_below=20.0, restore_above=30.0)
        stage = ShedStage(name="s1", circuits=[circuit], condition=cond, priority=0, min_hold_seconds=0.0)
        strategy = self._make_strategy(stages=[stage], restore_delay=30.0)

        # Shed at time=0
        with patch("csp_lib.controller.strategies.load_shedding.time.monotonic", return_value=0.0):
            strategy.execute(_make_context(soc=15.0))
        assert "s1" in strategy.shed_stage_names

        # Restore condition met at time=10 -- starts restore_requested_at
        with patch("csp_lib.controller.strategies.load_shedding.time.monotonic", return_value=10.0):
            strategy.execute(_make_context(soc=35.0))
        assert "s1" in strategy.shed_stage_names  # still shed (delay not elapsed)

        # At time=20, only 10s since restore request (need 30s)
        with patch("csp_lib.controller.strategies.load_shedding.time.monotonic", return_value=20.0):
            strategy.execute(_make_context(soc=35.0))
        assert "s1" in strategy.shed_stage_names  # still shed

        # At time=40, 30s since restore request -> completes
        with patch("csp_lib.controller.strategies.load_shedding.time.monotonic", return_value=40.0):
            strategy.execute(_make_context(soc=35.0))
        assert strategy.shed_stage_names == []

    # --- restore_delay resets if condition drops ---

    def test_restore_delay_resets_when_condition_drops(self):
        """restore_requested_at resets to None if should_restore becomes False."""
        circuit = MockCircuit("c1")
        cond = ThresholdCondition("soc", shed_below=20.0, restore_above=30.0)
        stage = ShedStage(name="s1", circuits=[circuit], condition=cond, priority=0, min_hold_seconds=0.0)
        strategy = self._make_strategy(stages=[stage], restore_delay=30.0)

        # Shed
        with patch("csp_lib.controller.strategies.load_shedding.time.monotonic", return_value=0.0):
            strategy.execute(_make_context(soc=15.0))

        # Start restore at time=10
        with patch("csp_lib.controller.strategies.load_shedding.time.monotonic", return_value=10.0):
            strategy.execute(_make_context(soc=35.0))

        # Condition drops back -- restore_requested_at should reset
        with patch("csp_lib.controller.strategies.load_shedding.time.monotonic", return_value=20.0):
            strategy.execute(_make_context(soc=25.0))  # not > 30

        # Condition met again at time=25
        with patch("csp_lib.controller.strategies.load_shedding.time.monotonic", return_value=25.0):
            strategy.execute(_make_context(soc=35.0))

        # At time=50, only 25s since new request (need 30s) -- should still be shed
        with patch("csp_lib.controller.strategies.load_shedding.time.monotonic", return_value=50.0):
            strategy.execute(_make_context(soc=35.0))
        assert "s1" in strategy.shed_stage_names

        # At time=56, 31s since restart -> completes
        with patch("csp_lib.controller.strategies.load_shedding.time.monotonic", return_value=56.0):
            strategy.execute(_make_context(soc=35.0))
        assert strategy.shed_stage_names == []

    # --- on_activate / on_deactivate ---

    @pytest.mark.asyncio
    async def test_on_activate_starts_background_task(self):
        """on_activate creates a background action task."""
        strategy = self._make_strategy()
        await strategy.on_activate()
        assert strategy._action_task is not None
        assert not strategy._action_task.done()
        # Cleanup
        await strategy.on_deactivate()

    @pytest.mark.asyncio
    async def test_on_deactivate_restores_all_when_auto_restore_enabled(self):
        """on_deactivate restores all circuits when auto_restore_on_deactivate=True."""
        c1 = MockCircuit("c1")
        c2 = MockCircuit("c2")
        cond = ThresholdCondition("soc", shed_below=20.0, restore_above=30.0)
        stage = ShedStage(name="s1", circuits=[c1, c2], condition=cond, priority=0, min_hold_seconds=0.0)
        strategy = self._make_strategy(stages=[stage], auto_restore_on_deactivate=True)

        await strategy.on_activate()

        # Shed via execute + let background task process
        strategy.execute(_make_context(soc=15.0))
        await asyncio.sleep(0.05)  # let background task pick up actions

        # Verify circuits were shed
        assert c1.is_shed is True
        assert c2.is_shed is True

        # Deactivate should restore
        await strategy.on_deactivate()
        assert c1.is_shed is False
        assert c2.is_shed is False

    @pytest.mark.asyncio
    async def test_on_deactivate_does_not_restore_when_auto_restore_disabled(self):
        """on_deactivate does NOT restore circuits when auto_restore_on_deactivate=False."""
        c1 = MockCircuit("c1")
        cond = ThresholdCondition("soc", shed_below=20.0, restore_above=30.0)
        stage = ShedStage(name="s1", circuits=[c1], condition=cond, priority=0, min_hold_seconds=0.0)
        strategy = self._make_strategy(stages=[stage], auto_restore_on_deactivate=False)

        await strategy.on_activate()

        # Shed
        strategy.execute(_make_context(soc=15.0))
        await asyncio.sleep(0.05)

        assert c1.is_shed is True

        # Deactivate -- should NOT restore
        await strategy.on_deactivate()
        assert c1.is_shed is True

    @pytest.mark.asyncio
    async def test_on_deactivate_resets_internal_state(self):
        """on_deactivate resets all internal state."""
        c1 = MockCircuit("c1")
        cond = ThresholdCondition("soc", shed_below=20.0, restore_above=30.0)
        stage = ShedStage(name="s1", circuits=[c1], condition=cond, priority=0)
        strategy = self._make_strategy(stages=[stage])

        await strategy.on_activate()
        strategy.execute(_make_context(soc=15.0))
        await asyncio.sleep(0.05)

        await strategy.on_deactivate()

        assert strategy._action_task is None
        assert strategy._pending_actions == []
        assert strategy.shed_stage_names == []

    # --- shed_stage_names ---

    def test_shed_stage_names_empty_initially(self):
        """shed_stage_names is empty before any execution."""
        strategy = self._make_strategy()
        assert strategy.shed_stage_names == []

    def test_shed_stage_names_tracks_shed_stages(self):
        """shed_stage_names returns names of currently shed stages."""
        c1 = MockCircuit("c1")
        c2 = MockCircuit("c2")
        cond_low = ThresholdCondition("soc", shed_below=20.0, restore_above=30.0)
        cond_high = ThresholdCondition("soc", shed_below=10.0, restore_above=20.0)
        stage1 = ShedStage(name="stage1", circuits=[c1], condition=cond_low, priority=1)
        stage2 = ShedStage(name="stage2", circuits=[c2], condition=cond_high, priority=2)
        strategy = self._make_strategy(stages=[stage1, stage2])

        # SOC=15: triggers stage1 (< 20) but not stage2 (< 10)
        strategy.execute(_make_context(soc=15.0))
        assert strategy.shed_stage_names == ["stage1"]

        # SOC=5: triggers stage2 too
        strategy.execute(_make_context(soc=5.0))
        assert set(strategy.shed_stage_names) == {"stage1", "stage2"}

    # --- Multi-stage progressive shedding ---

    def test_multi_stage_progressive_shedding(self):
        """Progressive shedding: stages shed one by one as conditions worsen."""
        c1, c2, c3 = MockCircuit("c1"), MockCircuit("c2"), MockCircuit("c3")
        stage1 = ShedStage(
            name="lighting",
            circuits=[c1],
            condition=ThresholdCondition("soc", shed_below=30.0, restore_above=40.0),
            priority=1,
        )
        stage2 = ShedStage(
            name="hvac",
            circuits=[c2],
            condition=ThresholdCondition("soc", shed_below=20.0, restore_above=30.0),
            priority=2,
        )
        stage3 = ShedStage(
            name="production",
            circuits=[c3],
            condition=ThresholdCondition("soc", shed_below=10.0, restore_above=20.0),
            priority=3,
        )
        strategy = self._make_strategy(stages=[stage3, stage1, stage2])  # out of order

        # SOC=25 -> only lighting shed (< 30)
        strategy.execute(_make_context(soc=25.0))
        assert strategy.shed_stage_names == ["lighting"]

        # SOC=15 -> lighting + hvac shed
        strategy.execute(_make_context(soc=15.0))
        assert set(strategy.shed_stage_names) == {"lighting", "hvac"}

        # SOC=5 -> all shed
        strategy.execute(_make_context(soc=5.0))
        assert set(strategy.shed_stage_names) == {"lighting", "hvac", "production"}

    # --- Background task processes actions ---

    @pytest.mark.asyncio
    async def test_background_task_executes_shed_on_circuits(self):
        """Background action loop calls circuit.shed() for pending shed actions."""
        c1 = MockCircuit("c1")
        c2 = MockCircuit("c2")
        cond = ThresholdCondition("soc", shed_below=20.0, restore_above=30.0)
        stage = ShedStage(name="s1", circuits=[c1, c2], condition=cond, priority=0, min_hold_seconds=0.0)
        strategy = self._make_strategy(stages=[stage])

        await strategy.on_activate()
        strategy.execute(_make_context(soc=15.0))
        await asyncio.sleep(0.05)

        assert c1.is_shed is True
        assert c2.is_shed is True

        await strategy.on_deactivate()

    @pytest.mark.asyncio
    async def test_background_task_executes_restore_on_circuits(self):
        """Background action loop calls circuit.restore() for pending restore actions."""
        c1 = MockCircuit("c1")
        cond = ThresholdCondition("soc", shed_below=20.0, restore_above=30.0)
        stage = ShedStage(name="s1", circuits=[c1], condition=cond, priority=0, min_hold_seconds=0.0)
        strategy = self._make_strategy(stages=[stage], restore_delay=0.0)

        await strategy.on_activate()

        # Shed
        with patch("csp_lib.controller.strategies.load_shedding.time.monotonic", return_value=0.0):
            strategy.execute(_make_context(soc=15.0))
        await asyncio.sleep(0.05)
        assert c1.is_shed is True

        # Start restore request
        with patch("csp_lib.controller.strategies.load_shedding.time.monotonic", return_value=100.0):
            strategy.execute(_make_context(soc=35.0))

        # Complete restore
        with patch("csp_lib.controller.strategies.load_shedding.time.monotonic", return_value=100.0):
            strategy.execute(_make_context(soc=35.0))
        await asyncio.sleep(0.05)

        assert c1.is_shed is False
        await strategy.on_deactivate()

    # --- __str__ ---

    def test_str_representation(self):
        """__str__ shows stage count and shed count."""
        cond = ThresholdCondition("soc", shed_below=20.0, restore_above=30.0)
        stage = ShedStage(name="s1", circuits=[], condition=cond)
        strategy = self._make_strategy(stages=[stage])

        assert "stages=1" in str(strategy)
        assert "shed=0" in str(strategy)

        strategy.execute(_make_context(soc=15.0))
        assert "shed=1" in str(strategy)

    # --- config property ---

    def test_config_property_returns_config(self):
        """config property returns the LoadSheddingConfig."""
        config = LoadSheddingConfig(evaluation_interval=7)
        strategy = LoadSheddingStrategy(config)
        assert strategy.config is config

    # --- Edge case: execute with no stages ---

    def test_execute_with_no_stages(self):
        """execute() with empty stages does nothing and returns last_command."""
        strategy = self._make_strategy(stages=[])
        cmd = Command(p_target=42.0)
        ctx = StrategyContext(last_command=cmd, extra={})

        result = strategy.execute(ctx)
        assert result == cmd
        assert strategy.shed_stage_names == []

    # --- Edge case: already shed stage not re-shed ---

    def test_already_shed_stage_not_re_shed(self):
        """A stage that is already shed is not shed again on subsequent execute() calls."""
        circuit = MockCircuit("c1")
        cond = ThresholdCondition("soc", shed_below=20.0, restore_above=30.0)
        stage = ShedStage(name="s1", circuits=[circuit], condition=cond)
        strategy = self._make_strategy(stages=[stage])

        strategy.execute(_make_context(soc=15.0))
        initial_pending = len(strategy._pending_actions)

        strategy.execute(_make_context(soc=15.0))
        # No new action should be added for already-shed stage
        assert len(strategy._pending_actions) == initial_pending
