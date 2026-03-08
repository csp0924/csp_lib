# =============== Equipment Device Tests - Point Toggle ===============
#
# 點位開關功能測試

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from csp_lib.equipment.alarm import (
    AlarmDefinition,
    AlarmLevel,
    Operator,
    ThresholdAlarmEvaluator,
    ThresholdCondition,
)
from csp_lib.equipment.core import ReadPoint, WritePoint
from csp_lib.equipment.device.base import AsyncModbusDevice
from csp_lib.equipment.device.config import DeviceConfig
from csp_lib.equipment.device.events import EVENT_POINT_TOGGLED, EVENT_VALUE_CHANGE
from csp_lib.equipment.transport import WriteStatus
from csp_lib.modbus import UInt16


@pytest.fixture
def mock_client() -> AsyncMock:
    client = AsyncMock()
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    client.read_holding_registers = AsyncMock(return_value=[100, 200])
    client.write_registers = AsyncMock()
    return client


@pytest.fixture
def device_config() -> DeviceConfig:
    return DeviceConfig(device_id="test_dev", unit_id=1, address_offset=0, read_interval=0.1)


@pytest.fixture
def read_points() -> list[ReadPoint]:
    return [
        ReadPoint(name="power", address=100, data_type=UInt16()),
        ReadPoint(name="voltage", address=101, data_type=UInt16()),
    ]


@pytest.fixture
def write_points() -> list[WritePoint]:
    return [
        WritePoint(name="setpoint", address=200, data_type=UInt16()),
    ]


@pytest.fixture
def alarm_evaluators() -> list[ThresholdAlarmEvaluator]:
    return [
        ThresholdAlarmEvaluator(
            point_name="power",
            conditions=[
                ThresholdCondition(
                    alarm=AlarmDefinition(code="HIGH_POWER", name="功率過高", level=AlarmLevel.WARNING),
                    operator=Operator.GT,
                    value=50.0,
                ),
            ],
        ),
    ]


@pytest.fixture
def device(mock_client, device_config, read_points, write_points, alarm_evaluators) -> AsyncModbusDevice:
    return AsyncModbusDevice(
        config=device_config,
        client=mock_client,
        always_points=read_points,
        write_points=write_points,
        alarm_evaluators=alarm_evaluators,
    )


class TestDisablePoint:
    """disable_point 測試"""

    def test_disable_point_adds_to_set(self, device):
        device.disable_point("power")
        assert "power" in device.disabled_points

    def test_disable_nonexistent_raises(self, device):
        with pytest.raises(KeyError, match="不存在"):
            device.disable_point("nonexistent")

    @pytest.mark.asyncio
    async def test_disabled_point_skipped_in_process_values(self, device):
        """disabled 點位不更新 _latest_values"""
        device.disable_point("power")
        await device._process_values({"power": 999, "voltage": 220})
        assert "power" not in device._latest_values
        assert device._latest_values["voltage"] == 220

    @pytest.mark.asyncio
    async def test_disabled_point_no_value_change_event(self, device):
        """disabled 點位不觸發 value_change 事件"""
        events = []

        async def handler(payload):
            events.append(payload)

        device.on(EVENT_VALUE_CHANGE, handler)
        await device._emitter.start()

        device.disable_point("power")
        await device._process_values({"power": 999, "voltage": 220})

        # 等事件處理完
        await asyncio.sleep(0.1)
        await device._emitter.stop()

        point_names = [e.point_name for e in events]
        assert "power" not in point_names
        assert "voltage" in point_names

    @pytest.mark.asyncio
    async def test_disabled_point_skipped_in_alarm_evaluation(self, device):
        """disabled 點位的 evaluator 不被評估"""
        device.disable_point("power")
        # 即使值超過閾值，也不應觸發告警
        await device._evaluate_alarm({"power": 100})
        assert len(device.active_alarms) == 0

    @pytest.mark.asyncio
    async def test_disabled_write_point_returns_validation_failed(self, device):
        """disabled 寫入點位回傳 VALIDATION_FAILED"""
        device.disable_point("setpoint")
        result = await device.write("setpoint", 42)
        assert result.status == WriteStatus.VALIDATION_FAILED
        assert "停用" in result.error_message


class TestEnablePoint:
    """enable_point 測試"""

    def test_enable_removes_from_disabled(self, device):
        device.disable_point("power")
        device.enable_point("power")
        assert "power" not in device.disabled_points

    def test_enable_nonexistent_raises(self, device):
        with pytest.raises(KeyError, match="不存在"):
            device.enable_point("nonexistent")

    @pytest.mark.asyncio
    async def test_re_enabled_point_processes_normally(self, device):
        """重新啟用後恢復正常處理"""
        device.disable_point("power")
        device.enable_point("power")
        await device._process_values({"power": 42})
        assert device._latest_values["power"] == 42


class TestIsPointEnabled:
    """is_point_enabled 測試"""

    def test_default_enabled(self, device):
        assert device.is_point_enabled("power") is True

    def test_disabled(self, device):
        device.disable_point("power")
        assert device.is_point_enabled("power") is False

    def test_re_enabled(self, device):
        device.disable_point("power")
        device.enable_point("power")
        assert device.is_point_enabled("power") is True


class TestPointToggledEvent:
    """EVENT_POINT_TOGGLED 事件測試"""

    @pytest.mark.asyncio
    async def test_disable_emits_event(self, device):
        events = []

        async def handler(payload):
            events.append(payload)

        device.on(EVENT_POINT_TOGGLED, handler)
        await device._emitter.start()

        device.disable_point("power")

        await asyncio.sleep(0.1)
        await device._emitter.stop()

        assert len(events) == 1
        assert events[0].point_name == "power"
        assert events[0].enabled is False

    @pytest.mark.asyncio
    async def test_enable_emits_event(self, device):
        events = []

        async def handler(payload):
            events.append(payload)

        device.on(EVENT_POINT_TOGGLED, handler)
        await device._emitter.start()

        device.disable_point("power")
        device.enable_point("power")

        await asyncio.sleep(0.1)
        await device._emitter.stop()

        assert len(events) == 2
        assert events[1].point_name == "power"
        assert events[1].enabled is True


class TestDisabledPointsProperty:
    """disabled_points property 測試"""

    def test_default_empty(self, device):
        assert device.disabled_points == frozenset()

    def test_returns_frozenset(self, device):
        device.disable_point("power")
        result = device.disabled_points
        assert isinstance(result, frozenset)
        assert result == frozenset({"power"})


class TestGetPointInfo:
    """get_point_info 測試"""

    def test_returns_all_points(self, device):
        infos = device.get_point_info()
        names = {info.name for info in infos}
        assert "power" in names
        assert "voltage" in names
        assert "setpoint" in names

    def test_reflects_enabled_state(self, device):
        device.disable_point("power")
        infos = device.get_point_info()
        power_info = next(i for i in infos if i.name == "power")
        voltage_info = next(i for i in infos if i.name == "voltage")
        assert power_info.enabled is False
        assert voltage_info.enabled is True

    def test_direction_read(self, device):
        infos = device.get_point_info()
        power_info = next(i for i in infos if i.name == "power")
        assert power_info.direction == "read"

    def test_direction_write(self, device):
        infos = device.get_point_info()
        setpoint_info = next(i for i in infos if i.name == "setpoint")
        assert setpoint_info.direction == "write"
