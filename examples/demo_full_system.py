"""
csp_lib Full System Demo

SimulationServer + AsyncModbusDevice + SystemController 端到端整合範例。

架構：
  SimulationServer (Modbus TCP 模擬器)
       ↕ TCP
  AsyncModbusDevice × 2 (PCS + 電表)
       ↓ read
  DeviceRegistry → ContextBuilder → StrategyContext
       ↓
  ModeManager (PQ 策略)
       ↓
  StrategyExecutor → Command
       ↓
  CommandRouter → device.write()
       ↓
  SimulationServer 接收寫入 → PCS 功率斜率追蹤

Run: uv run python examples/demo_full_system.py
"""

import asyncio

from csp_lib.controller.core import SystemBase
from csp_lib.controller.strategies import PQModeConfig, PQModeStrategy
from csp_lib.controller.system import ModePriority
from csp_lib.equipment.core import ReadPoint, WritePoint
from csp_lib.equipment.core.point import PointMetadata, RangeValidator
from csp_lib.equipment.device import AsyncModbusDevice, DeviceConfig
from csp_lib.integration import (
    CommandMapping,
    ContextMapping,
    DeviceRegistry,
    SystemController,
    SystemControllerConfig,
)
from csp_lib.modbus import Float32, ModbusTcpConfig, PymodbusTcpClient, UInt16
from csp_lib.modbus_server import (
    PCSSimulator,
    PowerMeterSimulator,
    ServerConfig,
    SimulationServer,
)
from csp_lib.modbus_server.simulator.pcs import default_pcs_config
from csp_lib.modbus_server.simulator.power_meter import default_meter_config

# ============================================================
# 常量：Modbus 連線配置
# ============================================================

SIM_HOST = "127.0.0.1"
SIM_PORT = 5020

# SimulationServer 預設 PCS (default_pcs_config) register 佈局：
#   p_setpoint:      addr=0,  Float32, writable
#   q_setpoint:      addr=2,  Float32, writable
#   p_actual:        addr=4,  Float32
#   q_actual:        addr=6,  Float32
#   soc:             addr=8,  Float32
#   operating_mode:  addr=10, UInt16
#   alarm_register_1:addr=11, UInt16
#   alarm_register_2:addr=12, UInt16
#   alarm_reset_cmd: addr=13, UInt16, writable
#   start_cmd:       addr=14, UInt16, writable
#   voltage:         addr=15, Float32
#   frequency:       addr=17, Float32

# SimulationServer 預設電表 (default_meter_config) register 佈局：
#   voltage_a:      addr=0,  Float32
#   voltage_b:      addr=2,  Float32
#   voltage_c:      addr=4,  Float32
#   current_a:      addr=6,  Float32
#   current_b:      addr=8,  Float32
#   current_c:      addr=10, Float32
#   active_power:   addr=12, Float32
#   reactive_power: addr=14, Float32
#   apparent_power: addr=16, Float32
#   power_factor:   addr=18, Float32
#   frequency:      addr=20, Float32
#   energy_total:   addr=22, Float32
#   status:         addr=24, UInt16


# ============================================================
# Step 1: 建立模擬器 (SimulationServer)
# ============================================================


def create_simulation_server() -> SimulationServer:
    """建立包含 PCS 和電表的模擬伺服器"""
    server = SimulationServer(ServerConfig(host=SIM_HOST, port=SIM_PORT, tick_interval=1.0))

    # PCS 模擬器 — unit_id=10, 初始 SOC=70%
    pcs_config = default_pcs_config(device_id="pcs_01", unit_id=10)
    pcs_sim = PCSSimulator(config=pcs_config, capacity_kwh=200.0, p_ramp_rate=50.0)
    # 設定初始 SOC
    pcs_sim.set_value("soc", 70.0)
    # 設定 PCS 為運行狀態（模擬器才會追蹤 setpoint）
    pcs_sim.set_value("operating_mode", 1)
    pcs_sim._running = True

    # 電表模擬器 — unit_id=1
    meter_config = default_meter_config(device_id="meter_01", unit_id=1)
    meter_sim = PowerMeterSimulator(config=meter_config, voltage_noise=1.5, frequency_noise=0.01)
    # 設定初始電表讀數
    meter_sim.set_system_reading(v=380.0, f=60.0, p=20.0, q=5.0)

    server.add_simulator(pcs_sim)
    server.add_simulator(meter_sim)

    return server


# ============================================================
# Step 2: 建立真實設備 (AsyncModbusDevice)
# ============================================================


def create_devices() -> tuple[AsyncModbusDevice, AsyncModbusDevice]:
    """建立 PCS 和電表的 AsyncModbusDevice（連接到模擬伺服器）"""

    # 共用同一個 TCP 連線設定
    tcp_config = ModbusTcpConfig(host=SIM_HOST, port=SIM_PORT, timeout=2.0)

    # --- PCS 設備 ---
    # ReadPoints 對應 PCSSimulator 的 register 佈局
    f32 = Float32()
    u16 = UInt16()

    pcs_read_points = [
        ReadPoint(
            name="p_actual",
            address=4,
            data_type=f32,
            metadata=PointMetadata(unit="kW", description="實際有功功率"),
        ),
        ReadPoint(
            name="q_actual",
            address=6,
            data_type=f32,
            metadata=PointMetadata(unit="kVar", description="實際無功功率"),
        ),
        ReadPoint(
            name="soc",
            address=8,
            data_type=f32,
            metadata=PointMetadata(unit="%", description="電池 SOC"),
        ),
        ReadPoint(
            name="operating_mode",
            address=10,
            data_type=u16,
            metadata=PointMetadata(description="運行模式", value_map={0: "Standby", 1: "Running"}),
        ),
        ReadPoint(
            name="voltage",
            address=15,
            data_type=f32,
            metadata=PointMetadata(unit="V", description="電壓"),
        ),
        ReadPoint(
            name="frequency",
            address=17,
            data_type=f32,
            metadata=PointMetadata(unit="Hz", description="頻率"),
        ),
    ]

    pcs_write_points = [
        WritePoint(
            name="p_set",
            address=0,
            data_type=f32,
            validator=RangeValidator(min_value=-200.0, max_value=200.0),
            metadata=PointMetadata(unit="kW", description="有功功率設定點"),
        ),
        WritePoint(
            name="q_set",
            address=2,
            data_type=f32,
            validator=RangeValidator(min_value=-100.0, max_value=100.0),
            metadata=PointMetadata(unit="kVar", description="無功功率設定點"),
        ),
    ]

    pcs_client = PymodbusTcpClient(tcp_config)
    pcs_device = AsyncModbusDevice(
        config=DeviceConfig(
            device_id="pcs_01",
            unit_id=10,
            read_interval=1.0,
            disconnect_threshold=5,
        ),
        client=pcs_client,
        always_points=pcs_read_points,
        write_points=pcs_write_points,
    )

    # --- 電表設備 ---
    meter_read_points = [
        ReadPoint(
            name="voltage",
            address=0,
            data_type=f32,
            metadata=PointMetadata(unit="V", description="A 相電壓"),
        ),
        ReadPoint(
            name="active_power",
            address=12,
            data_type=f32,
            metadata=PointMetadata(unit="kW", description="有功功率"),
        ),
        ReadPoint(
            name="frequency",
            address=20,
            data_type=f32,
            metadata=PointMetadata(unit="Hz", description="電網頻率"),
        ),
    ]

    meter_client = PymodbusTcpClient(tcp_config)
    meter_device = AsyncModbusDevice(
        config=DeviceConfig(
            device_id="meter_01",
            unit_id=1,
            read_interval=1.0,
            disconnect_threshold=5,
        ),
        client=meter_client,
        always_points=meter_read_points,
    )

    return pcs_device, meter_device


# ============================================================
# Step 3: 建立整合層 (Integration Layer)
# ============================================================


def create_controller(registry: DeviceRegistry) -> SystemController:
    """建立 SystemController，配置 context/command 映射和 PQ 策略"""

    config = SystemControllerConfig(
        # 設備讀取值 → StrategyContext 映射
        context_mappings=[
            ContextMapping(point_name="soc", context_field="soc", trait="pcs"),
            ContextMapping(point_name="voltage", context_field="extra.voltage", trait="meter"),
            ContextMapping(point_name="frequency", context_field="extra.frequency", trait="meter"),
            ContextMapping(point_name="active_power", context_field="extra.meter_power", trait="meter"),
        ],
        # Command → 設備寫入映射
        command_mappings=[
            CommandMapping(command_field="p_target", point_name="p_set", trait="pcs"),
            CommandMapping(command_field="q_target", point_name="q_set", trait="pcs"),
        ],
        # 系統額定容量
        system_base=SystemBase(p_base=200.0, q_base=100.0),
        # 控制週期
        auto_stop_on_alarm=False,
    )

    controller = SystemController(registry, config)

    # 註冊 PQ 策略：充電 30kW（放電為正，充電為負）
    controller.register_mode(
        "pq",
        PQModeStrategy(PQModeConfig(p=-30.0, q=0.0)),
        ModePriority.SCHEDULE,
        "PQ 模式: 充電 30kW",
    )

    return controller


# ============================================================
# Step 4: 事件處理器
# ============================================================


async def on_value_change(payload):
    """設備值變更事件"""
    # 只印出關鍵點位，避免輸出過多
    if payload.point_name in ("p_actual", "soc", "active_power"):
        print(f"  [value_change] {payload.device_id}.{payload.point_name}: {payload.old_value} -> {payload.new_value}")


# ============================================================
# Step 5: 主程式
# ============================================================


async def main():
    print("=" * 60)
    print("csp_lib Full System Demo")
    print("SimulationServer + AsyncModbusDevice + SystemController")
    print("=" * 60)

    # --- 1. 啟動模擬伺服器 ---
    print("\n[1/5] Starting SimulationServer...")
    server = create_simulation_server()

    async with server:
        print(f"  SimulationServer running on {SIM_HOST}:{SIM_PORT}")
        print(f"  Simulators: {list(server.simulators.keys())}")

        # 短暫等待 server 就緒
        await asyncio.sleep(0.5)

        # --- 2. 連接設備 ---
        print("\n[2/5] Connecting AsyncModbusDevice...")
        pcs_device, meter_device = create_devices()

        # 註冊事件處理器
        cancel_pcs_vc = pcs_device.on("value_change", on_value_change)
        cancel_meter_vc = meter_device.on("value_change", on_value_change)

        async with pcs_device, meter_device:
            print(f"  PCS  connected={pcs_device.is_connected}, responsive={pcs_device.is_responsive}")
            print(f"  Meter connected={meter_device.is_connected}, responsive={meter_device.is_responsive}")

            # 等待第一次讀取完成
            await asyncio.sleep(1.5)
            print(f"\n  PCS  latest_values: {pcs_device.latest_values}")
            print(f"  Meter latest_values: {meter_device.latest_values}")

            # --- 3. 建立整合層 ---
            print("\n[3/5] Building DeviceRegistry + SystemController...")
            registry = DeviceRegistry()
            registry.register(pcs_device, traits=["pcs"])
            registry.register(meter_device, traits=["meter"])

            controller = create_controller(registry)

            # 設定初始模式
            await controller.set_base_mode("pq")

            # --- 4. 啟動控制器 ---
            print("\n[4/5] Starting SystemController (PQ mode: P=-30kW charging)...")
            async with controller:
                print(f"  Controller running: {controller.is_running}")
                print(f"  Current mode: {controller.effective_mode_name}")

                # 讓控制迴圈執行數個週期
                for cycle in range(1, 8):
                    await asyncio.sleep(1.5)

                    # 讀取當前設備狀態
                    pcs_vals = pcs_device.latest_values
                    meter_vals = meter_device.latest_values

                    p_actual = pcs_vals.get("p_actual", "N/A")
                    soc = pcs_vals.get("soc", "N/A")
                    meter_p = meter_vals.get("active_power", "N/A")

                    # 格式化輸出
                    p_str = f"{p_actual:.1f}" if isinstance(p_actual, float) else str(p_actual)
                    soc_str = f"{soc:.1f}" if isinstance(soc, float) else str(soc)
                    mp_str = f"{meter_p:.1f}" if isinstance(meter_p, float) else str(meter_p)

                    print(f"  [cycle {cycle}] PCS: P_actual={p_str} kW, SOC={soc_str}% | Meter: P={mp_str} kW")

                    # 第 4 個週期切換策略: 放電 50kW
                    if cycle == 4:
                        print("\n  >>> Switching strategy: PQ mode P=+50kW (discharge) <<<")
                        controller.register_mode(
                            "pq_discharge",
                            PQModeStrategy(PQModeConfig(p=50.0, q=0.0)),
                            ModePriority.SCHEDULE,
                            "PQ 模式: 放電 50kW",
                        )
                        await controller.set_base_mode("pq_discharge")
                        print(f"  Current mode: {controller.effective_mode_name}")

            # --- 5. 清理 ---
            print("\n[5/5] SystemController stopped.")

        # 取消事件處理器
        cancel_pcs_vc()
        cancel_meter_vc()
        print("  Devices disconnected.")

    print("  SimulationServer stopped.")
    print("\n" + "=" * 60)
    print("Demo complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
