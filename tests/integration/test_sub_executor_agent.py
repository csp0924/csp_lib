# =============== SubExecutorAgent Protocol Tests ===============
#
# 測試 SubExecutorAgent Protocol 的定義與使用

from __future__ import annotations

import pytest

from csp_lib.controller.core import Command
from csp_lib.integration.hierarchical import DispatchCommand, ExecutorStatus, StatusReport, SubExecutorAgent
from csp_lib.integration.hierarchical.transport import DispatchPriority

# ============================================================
# Mock Implementation
# ============================================================


class MockSubExecutorAgent:
    """模擬子執行器代理，用於驗證 Protocol 介面"""

    def __init__(self, site_id: str) -> None:
        self._site_id = site_id
        self._last_dispatch: DispatchCommand | None = None
        self._overrides: list[str] = []
        self._healthy = True
        self._strategy_name = "pq"
        self._last_command = Command()
        self._running = True

    @property
    def site_id(self) -> str:
        return self._site_id

    async def dispatch(self, command: DispatchCommand) -> None:
        self._last_dispatch = command
        self._last_command = command.command

    async def get_status(self) -> ExecutorStatus:
        return ExecutorStatus(
            strategy_name=self._strategy_name,
            last_command=self._last_command,
            active_overrides=tuple(self._overrides),
            base_modes=("pq",),
            is_running=self._running,
            device_count=3,
            healthy_device_count=3,
        )

    async def push_override(self, mode_name: str) -> None:
        self._overrides.append(mode_name)

    async def pop_override(self, mode_name: str) -> None:
        if mode_name in self._overrides:
            self._overrides.remove(mode_name)

    async def health_check(self) -> bool:
        return self._healthy


# ============================================================
# Protocol Compliance Tests
# ============================================================


class TestSubExecutorAgentProtocol:
    """驗證 SubExecutorAgent Protocol 定義正確性"""

    def test_mock_implements_protocol(self):
        """MockSubExecutorAgent 符合 SubExecutorAgent Protocol"""
        agent = MockSubExecutorAgent("site_01")
        assert isinstance(agent, SubExecutorAgent)

    def test_protocol_is_runtime_checkable(self):
        """Protocol 為 runtime_checkable"""
        agent = MockSubExecutorAgent("site_01")
        assert isinstance(agent, SubExecutorAgent)

    def test_non_conforming_object_fails_check(self):
        """不符合 Protocol 的物件無法通過 isinstance 檢查"""

        class NotAnAgent:
            pass

        assert not isinstance(NotAnAgent(), SubExecutorAgent)

    def test_partial_implementation_fails(self):
        """僅實作部分方法的物件不符合 Protocol"""

        class PartialAgent:
            @property
            def site_id(self) -> str:
                return "partial"

            async def dispatch(self, command: DispatchCommand) -> None:
                pass

            # Missing: get_status, push_override, pop_override, health_check

        assert not isinstance(PartialAgent(), SubExecutorAgent)


# ============================================================
# Functional Tests
# ============================================================


class TestSubExecutorAgentFunctionality:
    """驗證 SubExecutorAgent 功能行為"""

    @pytest.fixture
    def agent(self) -> MockSubExecutorAgent:
        return MockSubExecutorAgent("site_bms")

    def test_site_id(self, agent: MockSubExecutorAgent):
        assert agent.site_id == "site_bms"

    @pytest.mark.asyncio
    async def test_dispatch_command(self, agent: MockSubExecutorAgent):
        cmd = DispatchCommand(
            source_site_id="scada",
            target_site_id="site_bms",
            command=Command(p_target=500.0, q_target=100.0),
        )
        await agent.dispatch(cmd)
        assert agent._last_dispatch is not None
        assert agent._last_dispatch.command.p_target == 500.0
        assert agent._last_dispatch.command.q_target == 100.0

    @pytest.mark.asyncio
    async def test_dispatch_updates_status(self, agent: MockSubExecutorAgent):
        cmd = DispatchCommand(
            source_site_id="scada",
            target_site_id="site_bms",
            command=Command(p_target=300.0, q_target=50.0),
        )
        await agent.dispatch(cmd)
        status = await agent.get_status()
        assert status.last_command.p_target == 300.0
        assert status.last_command.q_target == 50.0

    @pytest.mark.asyncio
    async def test_get_status(self, agent: MockSubExecutorAgent):
        status = await agent.get_status()
        assert status.strategy_name == "pq"
        assert status.is_running is True
        assert status.device_count == 3
        assert status.base_modes == ("pq",)

    @pytest.mark.asyncio
    async def test_push_and_pop_override(self, agent: MockSubExecutorAgent):
        await agent.push_override("stop")
        status = await agent.get_status()
        assert "stop" in status.active_overrides

        await agent.pop_override("stop")
        status = await agent.get_status()
        assert "stop" not in status.active_overrides

    @pytest.mark.asyncio
    async def test_multiple_overrides(self, agent: MockSubExecutorAgent):
        await agent.push_override("stop")
        await agent.push_override("bypass")
        status = await agent.get_status()
        assert len(status.active_overrides) == 2

    @pytest.mark.asyncio
    async def test_health_check(self, agent: MockSubExecutorAgent):
        assert await agent.health_check() is True
        agent._healthy = False
        assert await agent.health_check() is False


# ============================================================
# DispatchCommand Tests
# ============================================================


class TestDispatchCommand:
    """驗證 DispatchCommand 資料結構"""

    def test_create_basic(self):
        cmd = DispatchCommand(
            source_site_id="scada",
            target_site_id="site_01",
            command=Command(p_target=100.0, q_target=50.0),
        )
        assert cmd.source_site_id == "scada"
        assert cmd.target_site_id == "site_01"
        assert cmd.command.p_target == 100.0
        assert cmd.priority == DispatchPriority.NORMAL

    def test_frozen(self):
        cmd = DispatchCommand(
            source_site_id="scada",
            target_site_id="site_01",
            command=Command(),
        )
        with pytest.raises(AttributeError):
            cmd.source_site_id = "other"  # type: ignore[misc]

    def test_serialization_roundtrip(self):
        cmd = DispatchCommand(
            source_site_id="scada",
            target_site_id="site_bms",
            command=Command(p_target=500.0, q_target=100.0),
            priority=DispatchPriority.MANUAL,
            metadata={"correlation_id": "abc-123"},
        )
        data = cmd.to_dict()
        restored = DispatchCommand.from_dict(data)

        assert restored.source_site_id == cmd.source_site_id
        assert restored.target_site_id == cmd.target_site_id
        assert restored.command.p_target == cmd.command.p_target
        assert restored.command.q_target == cmd.command.q_target
        assert restored.priority == cmd.priority
        assert restored.metadata == cmd.metadata

    def test_priority_levels(self):
        assert DispatchPriority.NORMAL < DispatchPriority.SCHEDULE
        assert DispatchPriority.SCHEDULE < DispatchPriority.MANUAL
        assert DispatchPriority.MANUAL < DispatchPriority.PROTECTION

    def test_has_timestamp(self):
        cmd = DispatchCommand(
            source_site_id="scada",
            target_site_id="site_01",
            command=Command(),
        )
        assert cmd.timestamp is not None


# ============================================================
# StatusReport Tests
# ============================================================


class TestStatusReport:
    """驗證 StatusReport 資料結構"""

    def test_create_basic(self):
        status = ExecutorStatus(
            strategy_name="pq",
            last_command=Command(p_target=100.0),
            is_running=True,
        )
        report = StatusReport(site_id="site_01", status=status)
        assert report.site_id == "site_01"
        assert report.status.strategy_name == "pq"

    def test_frozen(self):
        report = StatusReport(
            site_id="site_01",
            status=ExecutorStatus(),
        )
        with pytest.raises(AttributeError):
            report.site_id = "other"  # type: ignore[misc]

    def test_serialization_roundtrip(self):
        report = StatusReport(
            site_id="site_bms",
            status=ExecutorStatus(
                strategy_name="cascading(pq+qv)",
                last_command=Command(p_target=600.0, q_target=250.0),
                active_overrides=("stop",),
                base_modes=("pq", "qv"),
                is_running=True,
                device_count=5,
                healthy_device_count=4,
            ),
            metrics={"soc": 80.0, "voltage": 379.0},
        )
        data = report.to_dict()
        restored = StatusReport.from_dict(data)

        assert restored.site_id == report.site_id
        assert restored.status.strategy_name == report.status.strategy_name
        assert restored.status.last_command.p_target == 600.0
        assert restored.status.last_command.q_target == 250.0
        assert restored.status.active_overrides == ("stop",)
        assert restored.status.base_modes == ("pq", "qv")
        assert restored.status.is_running is True
        assert restored.status.device_count == 5
        assert restored.status.healthy_device_count == 4
        assert restored.metrics["soc"] == 80.0

    def test_executor_status_defaults(self):
        status = ExecutorStatus()
        assert status.strategy_name == ""
        assert status.last_command.p_target == 0.0
        assert status.active_overrides == ()
        assert status.base_modes == ()
        assert status.is_running is False
        assert status.device_count == 0
