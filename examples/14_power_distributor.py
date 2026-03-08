"""
Example 14: PowerDistributor — 多機功率分配

Demonstrates:
  - EqualDistributor: split power equally across all devices
  - ProportionalDistributor: split proportional to rated capacity
  - SOCBalancingDistributor: proportional split with SOC-based P adjustment
  - Custom PowerDistributor: implement distribute() Protocol
  - SystemController integration: power_distributor in SystemControllerConfig
  - DeviceSnapshot: device state snapshot used during distribution

Scenario:
  A 3-unit BESS system with rated capacities 500kW / 1000kW / 500kW.
  Total system command: 1500kW discharge, 100kVar reactive.

  Compare how each distributor allocates power across the 3 units.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, PropertyMock

from csp_lib.controller.core import Command, SystemBase
from csp_lib.controller.strategies import PQModeConfig, PQModeStrategy
from csp_lib.controller.system import ModePriority
from csp_lib.integration import (
    CommandMapping,
    ContextMapping,
    DeviceRegistry,
    SystemController,
    SystemControllerConfig,
)
from csp_lib.integration.distributor import (
    DeviceSnapshot,
    EqualDistributor,
    ProportionalDistributor,
    SOCBalancingDistributor,
)

# ============================================================
# Shared test data
# ============================================================

SYSTEM_COMMAND = Command(p_target=1500.0, q_target=100.0)

# Device snapshots: 3 BESS units
DEVICES = [
    DeviceSnapshot(
        device_id="bess_01",
        metadata={"rated_p": 500.0, "rated_s": 600.0},
        latest_values={"soc": 80.0, "voltage": 380.0},
        capabilities={
            "soc_readable": {"soc": 80.0},
        },
    ),
    DeviceSnapshot(
        device_id="bess_02",
        metadata={"rated_p": 1000.0, "rated_s": 1200.0},
        latest_values={"soc": 60.0, "voltage": 380.0},
        capabilities={
            "soc_readable": {"soc": 60.0},
        },
    ),
    DeviceSnapshot(
        device_id="bess_03",
        metadata={"rated_p": 500.0, "rated_s": 600.0},
        latest_values={"soc": 40.0, "voltage": 380.0},
        capabilities={
            "soc_readable": {"soc": 40.0},
        },
    ),
]


def print_distribution(title: str, result: dict[str, Command]) -> None:
    print(f"\n  {title}:")
    total_p = 0.0
    total_q = 0.0
    for dev_id, cmd in result.items():
        snap = next(d for d in DEVICES if d.device_id == dev_id)
        soc = snap.capabilities.get("soc_readable", {}).get("soc", "N/A")
        rated = snap.metadata.get("rated_p", 0)
        print(f"    {dev_id} (rated={rated:.0f}kW, SOC={soc}%): P={cmd.p_target:+.1f}kW  Q={cmd.q_target:+.1f}kVar")
        total_p += cmd.p_target
        total_q += cmd.q_target
    print(f"    TOTAL: P={total_p:+.1f}kW  Q={total_q:+.1f}kVar")


# ============================================================
# Section A: EqualDistributor
# ============================================================


async def demo_equal_distributor():
    """
    EqualDistributor: split command equally regardless of rated capacity.

    Best for homogeneous fleets (all devices have same rated power).
    With 3 devices: each gets 1500/3=500kW, 100/3≈33.3kVar.
    """
    print("=" * 60)
    print("Section A: EqualDistributor")
    print("=" * 60)
    print(f"\n  System command: P={SYSTEM_COMMAND.p_target}kW, Q={SYSTEM_COMMAND.q_target}kVar")
    print("  Devices: bess_01 (500kW), bess_02 (1000kW), bess_03 (500kW)")
    print("  Note: EqualDistributor ignores rated capacity")

    distributor = EqualDistributor()
    result = distributor.distribute(SYSTEM_COMMAND, DEVICES)
    print_distribution("Equal distribution result", result)

    print("\n  Use case: homogeneous fleets where all devices have same spec")


# ============================================================
# Section B: ProportionalDistributor
# ============================================================


async def demo_proportional_distributor():
    """
    ProportionalDistributor: split proportional to rated_p metadata.

    Total rated: 500 + 1000 + 500 = 2000kW
    bess_01: 500/2000 = 25% → 375kW
    bess_02: 1000/2000 = 50% → 750kW
    bess_03: 500/2000 = 25% → 375kW
    """
    print("\n" + "=" * 60)
    print("Section B: ProportionalDistributor")
    print("=" * 60)
    print(f"\n  System command: P={SYSTEM_COMMAND.p_target}kW, Q={SYSTEM_COMMAND.q_target}kVar")
    print("  Devices: bess_01 (500kW), bess_02 (1000kW), bess_03 (500kW)")
    print("  Expected: 25% / 50% / 25% of system command")

    distributor = ProportionalDistributor(rated_key="rated_p")
    result = distributor.distribute(SYSTEM_COMMAND, DEVICES)
    print_distribution("Proportional distribution result", result)

    print("\n  Use case: heterogeneous fleets with different rated capacities")

    # Edge case: fallback when rated_p is missing
    print("\n  Edge case: devices without rated_p → fallback to EqualDistributor")
    no_metadata_devices = [
        DeviceSnapshot(device_id="bess_x", metadata={}, latest_values={}, capabilities={}),
        DeviceSnapshot(device_id="bess_y", metadata={}, latest_values={}, capabilities={}),
    ]
    result_fallback = distributor.distribute(SYSTEM_COMMAND, no_metadata_devices)
    for dev_id, cmd in result_fallback.items():
        print(f"    {dev_id}: P={cmd.p_target:.1f}kW (equal fallback)")


# ============================================================
# Section C: SOCBalancingDistributor
# ============================================================


async def demo_soc_balancing_distributor():
    """
    SOCBalancingDistributor: proportional base + SOC deviation adjustment.

    SOCs: bess_01=80%, bess_02=60%, bess_03=40%  → avg=60%
    Deviation: bess_01=+20%, bess_02=0%, bess_03=-20%

    Discharging (P>0): high SOC discharges more
      bess_01 factor = 1 + 2.0 * (20/100) = 1.4 → highest weight
      bess_02 factor = 1 + 2.0 * (0/100)  = 1.0
      bess_03 factor = 1 + 2.0 * (-20/100) = 0.6 → lowest weight

    P weights: 500*1.4=700, 1000*1.0=1000, 500*0.6=300 → total=2000
    bess_01: 700/2000 * 1500 = 525kW
    bess_02: 1000/2000 * 1500 = 750kW
    bess_03: 300/2000 * 1500 = 225kW
    """
    print("\n" + "=" * 60)
    print("Section C: SOCBalancingDistributor (discharge)")
    print("=" * 60)
    print(f"\n  System command: P={SYSTEM_COMMAND.p_target}kW (discharging), Q={SYSTEM_COMMAND.q_target}kVar")
    print("  SOCs: bess_01=80% (high), bess_02=60% (avg), bess_03=40% (low)")
    print("  High SOC → more discharge; Low SOC → less discharge")

    distributor = SOCBalancingDistributor(
        rated_key="rated_p",
        soc_capability="soc_readable",
        soc_slot="soc",
        gain=2.0,
    )
    result = distributor.distribute(SYSTEM_COMMAND, DEVICES)
    print_distribution("SOC-balanced discharge result", result)

    # Charging scenario (P<0): low SOC charges more
    charge_command = Command(p_target=-1500.0, q_target=-100.0)
    print(f"\n  Charging scenario: P={charge_command.p_target}kW")
    print("  Low SOC → more charging; High SOC → less charging")
    result_charge = distributor.distribute(charge_command, DEVICES)
    print_distribution("SOC-balanced charge result", result_charge)


# ============================================================
# Section D: Custom PowerDistributor
# ============================================================


async def demo_custom_distributor():
    """
    Custom PowerDistributor: implement distribute() to match any business rule.

    Example: temperature-based distribution.
    Cooler devices (lower temperature) receive more charging power.
    """
    print("\n" + "=" * 60)
    print("Section D: Custom PowerDistributor (temperature-based)")
    print("=" * 60)

    # Custom distributor: cooler device charges more
    class TemperatureDistributor:
        """Allocate charging power to cooler devices; equal for discharging."""

        def distribute(self, command: Command, devices: list[DeviceSnapshot]) -> dict[str, Command]:
            n = len(devices)
            if n == 0:
                return {}

            if command.p_target >= 0:
                # Discharging: equal split
                p_each = command.p_target / n
                q_each = command.q_target / n
                return {d.device_id: Command(p_target=p_each, q_target=q_each) for d in devices}
            else:
                # Charging: cooler device gets more (lower temp = higher weight)
                temps = [d.latest_values.get("temperature", 25.0) for d in devices]
                # Invert: weight = max_temp - temp + 1
                max_temp = max(temps)
                weights = [max_temp - t + 1.0 for t in temps]
                total_w = sum(weights)

                result = {}
                for d, w in zip(devices, weights, strict=True):
                    p_ratio = w / total_w
                    result[d.device_id] = Command(
                        p_target=command.p_target * p_ratio,
                        q_target=command.q_target / n,
                    )
                return result

    # Devices with temperature data
    devices_with_temp = [
        DeviceSnapshot(
            device_id="bess_01",
            metadata={"rated_p": 500.0},
            latest_values={"temperature": 45.0},  # Hot
            capabilities={},
        ),
        DeviceSnapshot(
            device_id="bess_02",
            metadata={"rated_p": 500.0},
            latest_values={"temperature": 30.0},  # Cool
            capabilities={},
        ),
        DeviceSnapshot(
            device_id="bess_03",
            metadata={"rated_p": 500.0},
            latest_values={"temperature": 25.0},  # Coolest
            capabilities={},
        ),
    ]

    distributor = TemperatureDistributor()

    charge_cmd = Command(p_target=-900.0, q_target=0.0)
    print(f"\n  Charging command: P={charge_cmd.p_target}kW")
    print("  Temperatures: bess_01=45°C (hot), bess_02=30°C, bess_03=25°C (cool)")
    print("  Cooler device receives more charging power:")
    result = distributor.distribute(charge_cmd, devices_with_temp)
    for dev_id, cmd in result.items():
        dev = next(d for d in devices_with_temp if d.device_id == dev_id)
        temp = dev.latest_values["temperature"]
        print(f"    {dev_id} ({temp}°C): P={cmd.p_target:+.1f}kW")


# ============================================================
# Section E: SystemController with PowerDistributor
# ============================================================


def make_mock_device(device_id: str, soc: float, rated_p: float) -> MagicMock:
    """Create a mock device for SystemController demo."""
    dev = MagicMock()
    type(dev).device_id = PropertyMock(return_value=device_id)
    type(dev).is_connected = PropertyMock(return_value=True)
    type(dev).is_responsive = PropertyMock(return_value=True)
    type(dev).is_protected = PropertyMock(return_value=False)
    type(dev).latest_values = PropertyMock(return_value={"soc": soc})
    type(dev).active_alarms = PropertyMock(return_value=[])
    type(dev).capabilities = PropertyMock(return_value={})
    dev.write = AsyncMock()
    dev.has_capability = lambda c: False

    def health():
        from csp_lib.core.health import HealthReport, HealthStatus

        return HealthReport(status=HealthStatus.HEALTHY, component=f"device:{device_id}", details={})

    dev.health = health
    return dev


async def demo_system_controller_integration():
    """
    Integrate PowerDistributor with SystemController.

    SystemController reads power_distributor from config and uses it
    to distribute the protected Command to individual devices when
    capability_command_mappings are configured.
    """
    print("\n" + "=" * 60)
    print("Section E: SystemController + ProportionalDistributor")
    print("=" * 60)

    bess_01 = make_mock_device("bess_01", soc=80.0, rated_p=500.0)
    bess_02 = make_mock_device("bess_02", soc=60.0, rated_p=1000.0)
    bms = make_mock_device("bms_01", soc=70.0, rated_p=0.0)

    registry = DeviceRegistry()
    # Provide rated_p as metadata for ProportionalDistributor
    registry.register(bess_01, traits=["pcs"], metadata={"rated_p": 500.0})
    registry.register(bess_02, traits=["pcs"], metadata={"rated_p": 1000.0})
    registry.register(bms, traits=["bms"])

    config = SystemControllerConfig(
        context_mappings=[
            ContextMapping(point_name="soc", context_field="soc", trait="bms"),
        ],
        command_mappings=[
            # Fallback command mapping (used when no capability_command_mappings)
            CommandMapping(command_field="p_target", point_name="p_setpoint", trait="pcs"),
        ],
        system_base=SystemBase(p_base=1500.0, q_base=750.0),
        # Enable proportional distribution across PCS devices
        power_distributor=ProportionalDistributor(rated_key="rated_p"),
    )

    controller = SystemController(registry, config)
    controller.register_mode(
        "pq",
        PQModeStrategy(PQModeConfig(p=1500.0, q=0.0)),
        ModePriority.SCHEDULE,
    )
    await controller.set_base_mode("pq")

    async with controller:
        await asyncio.sleep(2)
        print(f"\n  Controller running: {controller.is_running}")
        print(f"  Effective mode: {controller.effective_mode_name}")
        print("  System command: P=1500kW distributed across 2 PCS units")
        print("    bess_01 (rated=500kW) → expected ~500kW (1/3)")
        print("    bess_02 (rated=1000kW) → expected ~1000kW (2/3)")
        print("  Note: actual writes go to mock device.write() — no real hardware")

    print("  SystemController + PowerDistributor demo complete.")


# ============================================================
# Run all sections
# ============================================================


async def main():
    await demo_equal_distributor()
    await demo_proportional_distributor()
    await demo_soc_balancing_distributor()
    await demo_custom_distributor()
    await demo_system_controller_integration()

    print("\n" + "=" * 60)
    print("PowerDistributor Example Complete")
    print("=" * 60)
    print("\nDistributor selection guide:")
    print("  EqualDistributor         — homogeneous fleets (same rated_p)")
    print("  ProportionalDistributor  — heterogeneous fleets (different rated_p)")
    print("  SOCBalancingDistributor  — BESS with SOC balancing requirement")
    print("  Custom                   — any domain-specific logic")


if __name__ == "__main__":
    asyncio.run(main())
