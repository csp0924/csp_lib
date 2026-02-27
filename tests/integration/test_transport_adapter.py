# =============== TransportAdapter Protocol Tests ===============
#
# 測試 TransportAdapter Protocol 的定義與使用

from __future__ import annotations

from typing import Any, Awaitable, Callable

import pytest

from csp_lib.controller.core import Command
from csp_lib.integration.hierarchical import TransportAdapter
from csp_lib.integration.hierarchical.transport import DispatchCommand, DispatchPriority

# ============================================================
# Mock Implementation
# ============================================================


class MockTransportAdapter:
    """模擬傳輸層，用於驗證 Protocol 介面"""

    def __init__(self) -> None:
        self._connected = False
        self._published_commands: list[DispatchCommand] = []
        self._status_callbacks: list[Callable[[dict[str, Any]], Awaitable[None]]] = []
        self._healthy = True

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def publish_command(self, command: DispatchCommand) -> None:
        if not self._connected:
            raise RuntimeError("Not connected")
        self._published_commands.append(command)

    async def subscribe_status(
        self,
        callback: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        self._status_callbacks.append(callback)

    async def health_check(self) -> bool:
        return self._healthy and self._connected


# ============================================================
# Protocol Compliance Tests
# ============================================================


class TestTransportAdapterProtocol:
    """驗證 TransportAdapter Protocol 定義正確性"""

    def test_mock_implements_protocol(self):
        """MockTransportAdapter 符合 TransportAdapter Protocol"""
        adapter = MockTransportAdapter()
        assert isinstance(adapter, TransportAdapter)

    def test_protocol_is_runtime_checkable(self):
        """Protocol 為 runtime_checkable"""
        adapter = MockTransportAdapter()
        assert isinstance(adapter, TransportAdapter)

    def test_non_conforming_object_fails_check(self):
        """不符合 Protocol 的物件無法通過 isinstance 檢查"""

        class NotAnAdapter:
            pass

        assert not isinstance(NotAnAdapter(), TransportAdapter)

    def test_partial_implementation_fails(self):
        """僅實作部分方法不符合 Protocol"""

        class PartialAdapter:
            async def connect(self) -> None:
                pass

            async def disconnect(self) -> None:
                pass

            # Missing: publish_command, subscribe_status, health_check

        assert not isinstance(PartialAdapter(), TransportAdapter)


# ============================================================
# Functional Tests
# ============================================================


class TestTransportAdapterFunctionality:
    """驗證 TransportAdapter 功能行為"""

    @pytest.fixture
    def adapter(self) -> MockTransportAdapter:
        return MockTransportAdapter()

    @pytest.mark.asyncio
    async def test_connect_disconnect(self, adapter: MockTransportAdapter):
        assert not adapter._connected
        await adapter.connect()
        assert adapter._connected
        await adapter.disconnect()
        assert not adapter._connected

    @pytest.mark.asyncio
    async def test_publish_command(self, adapter: MockTransportAdapter):
        await adapter.connect()
        cmd = DispatchCommand(
            source_site_id="area_01",
            target_site_id="site_bms",
            command=Command(p_target=500.0, q_target=100.0),
        )
        await adapter.publish_command(cmd)
        assert len(adapter._published_commands) == 1
        assert adapter._published_commands[0].command.p_target == 500.0

    @pytest.mark.asyncio
    async def test_publish_requires_connection(self, adapter: MockTransportAdapter):
        cmd = DispatchCommand(
            source_site_id="area_01",
            target_site_id="site_bms",
            command=Command(),
        )
        with pytest.raises(RuntimeError, match="Not connected"):
            await adapter.publish_command(cmd)

    @pytest.mark.asyncio
    async def test_subscribe_status(self, adapter: MockTransportAdapter):
        received: list[dict[str, Any]] = []

        async def on_status(data: dict[str, Any]) -> None:
            received.append(data)

        await adapter.subscribe_status(on_status)
        assert len(adapter._status_callbacks) == 1

    @pytest.mark.asyncio
    async def test_health_check_connected(self, adapter: MockTransportAdapter):
        await adapter.connect()
        assert await adapter.health_check() is True

    @pytest.mark.asyncio
    async def test_health_check_disconnected(self, adapter: MockTransportAdapter):
        assert await adapter.health_check() is False

    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self, adapter: MockTransportAdapter):
        await adapter.connect()
        adapter._healthy = False
        assert await adapter.health_check() is False

    @pytest.mark.asyncio
    async def test_multiple_commands(self, adapter: MockTransportAdapter):
        await adapter.connect()
        for i in range(5):
            cmd = DispatchCommand(
                source_site_id="scada",
                target_site_id=f"site_{i}",
                command=Command(p_target=float(i * 100)),
            )
            await adapter.publish_command(cmd)
        assert len(adapter._published_commands) == 5

    @pytest.mark.asyncio
    async def test_dispatch_with_priority(self, adapter: MockTransportAdapter):
        await adapter.connect()
        cmd = DispatchCommand(
            source_site_id="scada",
            target_site_id="site_01",
            command=Command(p_target=0.0, q_target=0.0),
            priority=DispatchPriority.PROTECTION,
        )
        await adapter.publish_command(cmd)
        assert adapter._published_commands[0].priority == DispatchPriority.PROTECTION
