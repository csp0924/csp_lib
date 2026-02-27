"""
csp_lib Example 10: 分散式控制與指令編排

展示多群組控制與指令編排功能。

Section A — GroupControllerManager:
  - 2 台 PCS 模擬器（unit_id=10, 11）在同一台 SimulationServer 上
  - 2 個群組，各自擁有獨立的 SystemController
  - Group A: 充電 -30kW（PQ 模式）
  - Group B: 放電 +40kW（PQ 模式）
  - 各群組可獨立切換模式

Section B — SystemCommandOrchestrator:
  - 多步驟 SystemCommand（"startup_sequence"）：
    步驟 1: 設定 PCS 為待機（寫入 operating_mode=0）
    步驟 2: 驗證 PCS 響應（檢查條件）
    步驟 3: 切換至 PQ 模式並開始充電
  - 執行指令並顯示逐步進度
  - 展示成功與失敗（檢查逾時）場景

Run: uv run python examples/10_distributed_control.py
"""

import asyncio

from csp_lib.controller.core import SystemBase
from csp_lib.controller.strategies import PQModeConfig, PQModeStrategy, StopStrategy
from csp_lib.controller.system import ModePriority
from csp_lib.equipment.core import ReadPoint, WritePoint
from csp_lib.equipment.core.point import PointMetadata, RangeValidator
from csp_lib.equipment.device import AsyncModbusDevice, DeviceConfig
from csp_lib.integration import (
    CommandMapping,
    CommandStep,
    ContextMapping,
    DeviceRegistry,
    GroupControllerManager,
    GroupDefinition,
    StepCheck,
    SystemCommand,
    SystemCommandOrchestrator,
    SystemControllerConfig,
)
from csp_lib.modbus import Float32, ModbusTcpConfig, PymodbusTcpClient, UInt16
from csp_lib.modbus_server import PCSSimulator, ServerConfig, SimulationServer
from csp_lib.modbus_server.simulator.pcs import default_pcs_config

# ============================================================
# 常量
# ============================================================

SIM_HOST = "127.0.0.1"
SIM_PORT = 5021  # 使用不同 port 避免與 demo_full_system 衝突

f32 = Float32()
u16 = UInt16()


# ============================================================
# PCS 設備子類別（帶有編排器用的 ACTIONS）
# ============================================================


class PCSDevice(AsyncModbusDevice):
    """PCS 設備，帶有 SystemCommandOrchestrator 所需的 action 支援。"""

    ACTIONS: dict[str, str] = {
        "set_standby": "_action_set_standby",
        "set_running": "_action_set_running",
    }

    async def _action_set_standby(self) -> None:
        """透過 start_cmd 寫入 operating_mode=0（待機）。"""
        await self.write("start_cmd", 0)

    async def _action_set_running(self) -> None:
        """透過 start_cmd 寫入 operating_mode=1（運行）。"""
        await self.write("start_cmd", 1)


# ============================================================
# 輔助函式：SimulationServer、設備、控制器
# ============================================================


def create_simulation_server() -> SimulationServer:
    """建立包含 2 台 PCS 模擬器（unit_id=10, 11）的模擬伺服器。"""
    server = SimulationServer(ServerConfig(host=SIM_HOST, port=SIM_PORT, tick_interval=1.0))

    for idx, uid in enumerate([10, 11], start=1):
        pcs_config = default_pcs_config(device_id=f"pcs_{idx:02d}", unit_id=uid)
        pcs_sim = PCSSimulator(config=pcs_config, capacity_kwh=200.0, p_ramp_rate=50.0)
        pcs_sim.set_value("soc", 60.0 + idx * 5)  # PCS1: 65%, PCS2: 70%
        pcs_sim.set_value("operating_mode", 1)
        pcs_sim._running = True
        server.add_simulator(pcs_sim)

    return server


def create_pcs_device(device_id: str, unit_id: int) -> PCSDevice:
    """建立連接到模擬伺服器的 PCSDevice。"""
    tcp_config = ModbusTcpConfig(host=SIM_HOST, port=SIM_PORT, timeout=2.0)

    read_points = [
        ReadPoint(name="p_actual", address=4, data_type=f32, metadata=PointMetadata(unit="kW")),
        ReadPoint(name="q_actual", address=6, data_type=f32, metadata=PointMetadata(unit="kVar")),
        ReadPoint(name="soc", address=8, data_type=f32, metadata=PointMetadata(unit="%")),
        ReadPoint(name="operating_mode", address=10, data_type=u16, metadata=PointMetadata(description="運行模式")),
    ]

    write_points = [
        WritePoint(
            name="p_set",
            address=0,
            data_type=f32,
            validator=RangeValidator(min_value=-200.0, max_value=200.0),
            metadata=PointMetadata(unit="kW"),
        ),
        WritePoint(
            name="q_set",
            address=2,
            data_type=f32,
            validator=RangeValidator(min_value=-100.0, max_value=100.0),
            metadata=PointMetadata(unit="kVar"),
        ),
        WritePoint(
            name="start_cmd",
            address=14,
            data_type=u16,
            metadata=PointMetadata(description="啟停指令"),
        ),
    ]

    client = PymodbusTcpClient(tcp_config)
    return PCSDevice(
        config=DeviceConfig(device_id=device_id, unit_id=unit_id, read_interval=1.0, disconnect_threshold=5),
        client=client,
        always_points=read_points,
        write_points=write_points,
    )


def create_group_config(group_label: str) -> SystemControllerConfig:
    """建立單一 PCS 群組的最小 SystemControllerConfig。"""
    return SystemControllerConfig(
        context_mappings=[
            ContextMapping(point_name="soc", context_field="soc", trait="pcs"),
        ],
        command_mappings=[
            CommandMapping(command_field="p_target", point_name="p_set", trait="pcs"),
            CommandMapping(command_field="q_target", point_name="q_set", trait="pcs"),
        ],
        system_base=SystemBase(p_base=200.0, q_base=100.0),
        auto_stop_on_alarm=False,
    )


# ============================================================
# Section A: GroupControllerManager（群組控制管理器）
# ============================================================


async def section_a(pcs1: PCSDevice, pcs2: PCSDevice) -> None:
    """展示 GroupControllerManager 管理 2 個獨立群組。"""
    print("=" * 70)
    print("  Section A: GroupControllerManager")
    print("  兩個 PCS 群組，各自擁有獨立策略")
    print("=" * 70)

    # -- 建立主設備註冊表 --
    registry = DeviceRegistry()
    registry.register(pcs1, traits=["pcs"])
    registry.register(pcs2, traits=["pcs"])

    # -- 定義群組 --
    # 每個群組恰好有一台 PCS 和自己的 SystemController。
    # GroupControllerManager 會自動建立子註冊表。
    group_a_config = create_group_config("Group A")
    group_b_config = create_group_config("Group B")

    groups = [
        GroupDefinition(group_id="group_a", device_ids=["pcs_01"], config=group_a_config),
        GroupDefinition(group_id="group_b", device_ids=["pcs_02"], config=group_b_config),
    ]

    gcm = GroupControllerManager(registry=registry, groups=groups)
    print(f"\n  Groups created: {gcm.group_ids}")
    print(f"  Total groups: {len(gcm)}")

    # -- 為各群組註冊策略 --
    # Group A: 充電 -30 kW
    gcm.register_mode("group_a", "pq_charge", PQModeStrategy(PQModeConfig(p=-30.0, q=0.0)), ModePriority.SCHEDULE)
    # Group B: 放電 +40 kW
    gcm.register_mode("group_b", "pq_discharge", PQModeStrategy(PQModeConfig(p=40.0, q=0.0)), ModePriority.SCHEDULE)
    # 另外為 Group A 註冊停止模式（稍後使用）
    gcm.register_mode("group_a", "stop", StopStrategy(), ModePriority.MANUAL)

    # -- 設定基礎模式 --
    await gcm.set_base_mode("group_a", "pq_charge")
    await gcm.set_base_mode("group_b", "pq_discharge")

    # -- 啟動 GroupControllerManager --
    async with gcm:
        print(f"\n  GroupControllerManager running: {gcm.is_running}")
        print(f"  Group A mode: {gcm.effective_mode_name('group_a')}")
        print(f"  Group B mode: {gcm.effective_mode_name('group_b')}")

        # -- 觀察 3 個週期的獨立運行 --
        for cycle in range(1, 4):
            await asyncio.sleep(1.5)
            vals_a = pcs1.latest_values
            vals_b = pcs2.latest_values
            p_a = vals_a.get("p_actual", 0.0)
            p_b = vals_b.get("p_actual", 0.0)
            soc_a = vals_a.get("soc", 0.0)
            soc_b = vals_b.get("soc", 0.0)
            p_a_str = f"{p_a:.1f}" if isinstance(p_a, (int, float)) else str(p_a)
            p_b_str = f"{p_b:.1f}" if isinstance(p_b, (int, float)) else str(p_b)
            soc_a_str = f"{soc_a:.1f}" if isinstance(soc_a, (int, float)) else str(soc_a)
            soc_b_str = f"{soc_b:.1f}" if isinstance(soc_b, (int, float)) else str(soc_b)
            print(
                f"  [cycle {cycle}] "
                f"Group A: P={p_a_str} kW, SOC={soc_a_str}% | "
                f"Group B: P={p_b_str} kW, SOC={soc_b_str}%"
            )

        # -- 將 Group A 切換為停止模式（覆蓋），Group B 不受影響 --
        print("\n  >>> 對 Group A 推入 'stop' 覆蓋（Group B 不受影響）<<<")
        await gcm.push_override("group_a", "stop")
        print(f"  Group A mode: {gcm.effective_mode_name('group_a')}")
        print(f"  Group B mode: {gcm.effective_mode_name('group_b')}")

        for cycle in range(4, 6):
            await asyncio.sleep(1.5)
            vals_a = pcs1.latest_values
            vals_b = pcs2.latest_values
            p_a = vals_a.get("p_actual", 0.0)
            p_b = vals_b.get("p_actual", 0.0)
            p_a_str = f"{p_a:.1f}" if isinstance(p_a, (int, float)) else str(p_a)
            p_b_str = f"{p_b:.1f}" if isinstance(p_b, (int, float)) else str(p_b)
            print(f"  [cycle {cycle}] Group A: P={p_a_str} kW (停止中) | Group B: P={p_b_str} kW (持續放電)")

        # -- 彈出覆蓋，Group A 恢復充電 --
        print("\n  >>> 彈出 Group A 的 'stop' 覆蓋 <<<")
        await gcm.pop_override("group_a", "stop")
        print(f"  Group A mode: {gcm.effective_mode_name('group_a')}")

        # -- 健康狀態報告 --
        health = gcm.health()
        print(f"\n  群組健康狀態: {health.status.name}")
        for child in health.children:
            print(f"    {child.component}: {child.status.name}")

    print("\n  GroupControllerManager stopped.\n")


# ============================================================
# Section B: SystemCommandOrchestrator（系統指令編排器）
# ============================================================


async def section_b(pcs1: PCSDevice) -> None:
    """展示 SystemCommandOrchestrator 的多步驟指令編排。"""
    print("=" * 70)
    print("  Section B: SystemCommandOrchestrator")
    print("  多步驟指令序列（含檢查）")
    print("=" * 70)

    # -- 僅使用 PCS1 建立註冊表 --
    registry = DeviceRegistry()
    registry.register(pcs1, traits=["pcs"])

    orchestrator = SystemCommandOrchestrator(registry)

    # ---- 定義成功的啟動序列 ----
    startup_cmd = SystemCommand(
        name="startup_sequence",
        description="完整 PCS 啟動: 待機 -> 驗證 -> 充電",
        steps=[
            # 步驟 1: 設定 PCS 為待機（透過 start_cmd 寫入 operating_mode=0）
            CommandStep(
                action="set_standby",
                trait="pcs",
                description="設定 PCS 為待機模式",
            ),
            # 步驟 2: 驗證 PCS 已響應（應立即通過）
            CommandStep(
                action="set_running",
                trait="pcs",
                delay_before=0.5,
                description="啟動 PCS（設定為運行模式）",
                check_after=StepCheck(
                    trait="pcs",
                    check="is_responsive",
                    timeout=3.0,
                    poll_interval=0.5,
                ),
            ),
            # 步驟 3: 確認 PCS 運行中，準備充電
            # 由於沒有 "charge" action，這裡展示直接方式：
            # 編排器呼叫 execute_action，PCS 運行後由 SystemController 策略處理實際功率設定。
            CommandStep(
                action="set_running",
                trait="pcs",
                delay_before=0.5,
                description="確認 PCS 運行中，準備充電就緒",
            ),
        ],
    )
    orchestrator.register(startup_cmd)

    # ---- 執行啟動序列（成功場景）----
    print("\n  [成功場景] 執行 'startup_sequence'...")
    print(f"  已註冊指令: {orchestrator.registered_commands}")
    result = await orchestrator.execute("startup_sequence")

    print(f"\n  Command: {result.command_name}")
    print(f"  Status:  {result.status}")
    for sr in result.step_results:
        check_info = ""
        if sr.check_passed is not None:
            check_info = f", check={'PASS' if sr.check_passed else 'FAIL'}"
        print(f"    Step {sr.step_index}: [{sr.status}] {sr.description}{check_info}")
        if sr.device_results:
            for did, dres in sr.device_results.items():
                print(f"      {did}: {dres}")

    # ---- 定義會在檢查階段失敗的指令 ----
    print("\n  " + "-" * 50)
    print("  [失敗場景] 帶有無法達成檢查條件的指令...")

    fail_cmd = SystemCommand(
        name="fail_check_demo",
        description="演示: 步驟成功但健康檢查逾時",
        steps=[
            CommandStep(
                action="set_standby",
                trait="pcs",
                description="設定 PCS 為待機",
                check_after=StepCheck(
                    trait="pcs",
                    # 檢查不存在的屬性以強制逾時
                    check="is_at_full_power",
                    timeout=1.5,
                    poll_interval=0.5,
                ),
            ),
        ],
    )
    orchestrator.register(fail_cmd)

    result_fail = await orchestrator.execute("fail_check_demo")

    print(f"\n  Command: {result_fail.command_name}")
    print(f"  Status:  {result_fail.status}")
    if result_fail.aborted_at_step is not None:
        print(f"  Aborted at step: {result_fail.aborted_at_step}")
    if result_fail.error_message:
        print(f"  Error: {result_fail.error_message}")
    for sr in result_fail.step_results:
        check_info = ""
        if sr.check_passed is not None:
            check_info = f", check={'PASS' if sr.check_passed else 'FAIL'}"
        print(f"    Step {sr.step_index}: [{sr.status}] {sr.description}{check_info}")
        if sr.error_message:
            print(f"      Error: {sr.error_message}")

    print()


# ============================================================
# 主程式
# ============================================================


async def main() -> None:
    print()
    print("=" * 70)
    print("  csp_lib Example 10: Distributed Control & Orchestration")
    print("=" * 70)

    # -- 啟動 SimulationServer --
    print("\n  啟動 SimulationServer（含 2 台 PCS 模擬器）...")
    server = create_simulation_server()

    async with server:
        print(f"  Server running on {SIM_HOST}:{SIM_PORT}")
        print(f"  Simulators: {list(server.simulators.keys())}")
        await asyncio.sleep(0.5)

        # -- 連接設備 --
        pcs1 = create_pcs_device("pcs_01", unit_id=10)
        pcs2 = create_pcs_device("pcs_02", unit_id=11)

        async with pcs1, pcs2:
            print(f"  PCS1 connected={pcs1.is_connected}, responsive={pcs1.is_responsive}")
            print(f"  PCS2 connected={pcs2.is_connected}, responsive={pcs2.is_responsive}")

            # 等待第一次讀取完成
            await asyncio.sleep(1.5)
            print(f"  PCS1 values: {pcs1.latest_values}")
            print(f"  PCS2 values: {pcs2.latest_values}")

            # -- Section A: GroupControllerManager --
            print()
            await section_a(pcs1, pcs2)

            # 段落間短暫暫停
            await asyncio.sleep(0.5)

            # -- Section B: SystemCommandOrchestrator --
            await section_b(pcs1)

        print("  設備已斷線。")
    print("  SimulationServer 已停止。")

    print()
    print("=" * 70)
    print("  Demo complete!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
