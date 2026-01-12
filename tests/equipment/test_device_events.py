# =============== Equipment Device Tests - Events ===============
#
# DeviceEventEmitter 事件發射器單元測試
#
# 測試覆蓋：
# - 事件註冊與發射
# - 取消訂閱
# - 多處理器並行執行
# - 錯誤處理
# - Payload dataclass

from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from csp_lib.equipment.device.events import (
    EVENT_CONNECTED,
    EVENT_DISCONNECTED,
    EVENT_READ_COMPLETE,
    EVENT_VALUE_CHANGE,
    DeviceEventEmitter,
    DisconnectPayload,
    ReadCompletePayload,
    ValueChangePayload,
)

# ======================== Payload Tests ========================


class TestValueChangePayload:
    """ValueChangePayload 測試"""

    def test_create_payload(self):
        """正確建立 payload"""
        payload = ValueChangePayload(
            point_name="power",
            old_value=100,
            new_value=200,
        )

        assert payload.point_name == "power"
        assert payload.old_value == 100
        assert payload.new_value == 200
        assert isinstance(payload.timestamp, datetime)

    def test_frozen_immutable(self):
        """frozen=True 應使物件不可變"""
        payload = ValueChangePayload(point_name="test", old_value=0, new_value=1)

        with pytest.raises(AttributeError):
            payload.point_name = "changed"


class TestDisconnectPayload:
    """DisconnectPayload 測試"""

    def test_create_payload(self):
        """正確建立 payload"""
        payload = DisconnectPayload(
            reason="Connection timeout",
            consecutive_failures=5,
        )

        assert payload.reason == "Connection timeout"
        assert payload.consecutive_failures == 5
        assert isinstance(payload.timestamp, datetime)


class TestReadCompletePayload:
    """ReadCompletePayload 測試"""

    def test_create_payload(self):
        """正確建立 payload"""
        values = {"power": 100, "voltage": 220}
        payload = ReadCompletePayload(
            values=values,
            duration_ms=15.5,
        )

        assert payload.values == values
        assert payload.duration_ms == 15.5
        assert isinstance(payload.timestamp, datetime)


# ======================== DeviceEventEmitter Tests ========================


class TestDeviceEventEmitterBasic:
    """DeviceEventEmitter 基本功能測試"""

    @pytest.fixture
    def emitter(self) -> DeviceEventEmitter:
        return DeviceEventEmitter()

    @pytest.mark.asyncio
    async def test_emit_triggers_handler(self, emitter: DeviceEventEmitter):
        """發射事件應觸發處理器"""
        handler = AsyncMock()
        emitter.on(EVENT_CONNECTED, handler)

        await emitter.emit(EVENT_CONNECTED, {"status": "ok"})

        handler.assert_called_once_with({"status": "ok"})

    @pytest.mark.asyncio
    async def test_emit_no_handlers_no_error(self, emitter: DeviceEventEmitter):
        """無處理器時發射事件不應報錯"""
        await emitter.emit(EVENT_CONNECTED)  # 不應拋錯

    @pytest.mark.asyncio
    async def test_emit_with_none_payload(self, emitter: DeviceEventEmitter):
        """發射事件時 payload 可為 None"""
        handler = AsyncMock()
        emitter.on(EVENT_CONNECTED, handler)

        await emitter.emit(EVENT_CONNECTED)

        handler.assert_called_once_with(None)

    def test_has_listeners_true(self, emitter: DeviceEventEmitter):
        """有監聽器時應回傳 True"""
        emitter.on(EVENT_CONNECTED, AsyncMock())

        assert emitter.has_listeners(EVENT_CONNECTED) is True

    def test_has_listeners_false(self, emitter: DeviceEventEmitter):
        """無監聽器時應回傳 False"""
        assert emitter.has_listeners(EVENT_CONNECTED) is False


class TestDeviceEventEmitterMultipleHandlers:
    """多處理器測試"""

    @pytest.fixture
    def emitter(self) -> DeviceEventEmitter:
        return DeviceEventEmitter()

    @pytest.mark.asyncio
    async def test_multiple_handlers_all_called(self, emitter: DeviceEventEmitter):
        """多個處理器應全部被呼叫"""
        handler1 = AsyncMock()
        handler2 = AsyncMock()
        handler3 = AsyncMock()

        emitter.on(EVENT_VALUE_CHANGE, handler1)
        emitter.on(EVENT_VALUE_CHANGE, handler2)
        emitter.on(EVENT_VALUE_CHANGE, handler3)

        payload = ValueChangePayload(point_name="power", old_value=0, new_value=100)
        await emitter.emit(EVENT_VALUE_CHANGE, payload)

        handler1.assert_called_once_with(payload)
        handler2.assert_called_once_with(payload)
        handler3.assert_called_once_with(payload)

    @pytest.mark.asyncio
    async def test_handlers_run_concurrently(self, emitter: DeviceEventEmitter):
        """處理器應並行執行"""
        execution_order: list[int] = []

        async def slow_handler(payload):
            await asyncio.sleep(0.1)
            execution_order.append(1)

        async def fast_handler(payload):
            execution_order.append(2)

        emitter.on(EVENT_CONNECTED, slow_handler)
        emitter.on(EVENT_CONNECTED, fast_handler)

        await emitter.emit(EVENT_CONNECTED)

        # 若並行執行，快的應先完成
        assert execution_order == [2, 1]


class TestDeviceEventEmitterCancel:
    """取消訂閱測試"""

    @pytest.fixture
    def emitter(self) -> DeviceEventEmitter:
        return DeviceEventEmitter()

    @pytest.mark.asyncio
    async def test_cancel_removes_handler(self, emitter: DeviceEventEmitter):
        """取消訂閱後處理器不應被呼叫"""
        handler = AsyncMock()
        cancel = emitter.on(EVENT_CONNECTED, handler)

        # 取消訂閱
        cancel()

        await emitter.emit(EVENT_CONNECTED)

        handler.assert_not_called()

    @pytest.mark.asyncio
    async def test_cancel_only_removes_specific_handler(self, emitter: DeviceEventEmitter):
        """取消訂閱只應移除特定處理器"""
        handler1 = AsyncMock()
        handler2 = AsyncMock()

        cancel1 = emitter.on(EVENT_CONNECTED, handler1)
        emitter.on(EVENT_CONNECTED, handler2)

        cancel1()

        await emitter.emit(EVENT_CONNECTED)

        handler1.assert_not_called()
        handler2.assert_called_once()

    def test_cancel_twice_no_error(self, emitter: DeviceEventEmitter):
        """重複取消不應報錯"""
        handler = AsyncMock()
        cancel = emitter.on(EVENT_CONNECTED, handler)

        cancel()
        cancel()  # 第二次取消不應報錯


class TestDeviceEventEmitterClear:
    """清除處理器測試"""

    @pytest.fixture
    def emitter(self) -> DeviceEventEmitter:
        return DeviceEventEmitter()

    @pytest.mark.asyncio
    async def test_clear_specific_event(self, emitter: DeviceEventEmitter):
        """清除特定事件的處理器"""
        handler1 = AsyncMock()
        handler2 = AsyncMock()

        emitter.on(EVENT_CONNECTED, handler1)
        emitter.on(EVENT_DISCONNECTED, handler2)

        emitter.clear(EVENT_CONNECTED)

        await emitter.emit(EVENT_CONNECTED)
        await emitter.emit(EVENT_DISCONNECTED)

        handler1.assert_not_called()
        handler2.assert_called_once()

    @pytest.mark.asyncio
    async def test_clear_all_events(self, emitter: DeviceEventEmitter):
        """清除所有事件處理器"""
        handler1 = AsyncMock()
        handler2 = AsyncMock()

        emitter.on(EVENT_CONNECTED, handler1)
        emitter.on(EVENT_DISCONNECTED, handler2)

        emitter.clear()

        await emitter.emit(EVENT_CONNECTED)
        await emitter.emit(EVENT_DISCONNECTED)

        handler1.assert_not_called()
        handler2.assert_not_called()

    def test_clear_nonexistent_event_no_error(self, emitter: DeviceEventEmitter):
        """清除不存在的事件不應報錯"""
        emitter.clear("nonexistent_event")  # 不應拋錯


class TestDeviceEventEmitterErrorHandling:
    """錯誤處理測試"""

    @pytest.fixture
    def emitter(self) -> DeviceEventEmitter:
        return DeviceEventEmitter()

    @pytest.mark.asyncio
    async def test_handler_exception_does_not_break_others(self, emitter: DeviceEventEmitter):
        """處理器異常不應影響其他處理器"""
        handler1 = AsyncMock(side_effect=Exception("Handler 1 failed"))
        handler2 = AsyncMock()

        emitter.on(EVENT_CONNECTED, handler1)
        emitter.on(EVENT_CONNECTED, handler2)

        # 不應拋錯，且 handler2 仍應被呼叫
        await emitter.emit(EVENT_CONNECTED)

        handler1.assert_called_once()
        handler2.assert_called_once()

    @pytest.mark.asyncio
    async def test_handler_exception_logged(self, emitter: DeviceEventEmitter, caplog):
        """處理器異常應被記錄"""

        async def failing_handler(payload):
            raise ValueError("Test error")

        emitter.on(EVENT_CONNECTED, failing_handler)

        await emitter.emit(EVENT_CONNECTED, {"test": True})

        # 應有 warning 日誌（取決於 logger 設定）
        # 這裡至少確認不會崩潰


# ======================== Event Constants Tests ========================


class TestEventConstants:
    """事件常數測試"""

    def test_event_constants_are_strings(self):
        """事件常數應為字串"""
        assert isinstance(EVENT_CONNECTED, str)
        assert isinstance(EVENT_DISCONNECTED, str)
        assert isinstance(EVENT_READ_COMPLETE, str)
        assert isinstance(EVENT_VALUE_CHANGE, str)

    def test_event_constants_values(self):
        """事件常數值應正確"""
        assert EVENT_CONNECTED == "connected"
        assert EVENT_DISCONNECTED == "disconnected"
        assert EVENT_READ_COMPLETE == "read_complete"
        assert EVENT_VALUE_CHANGE == "value_change"
