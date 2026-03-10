"""
Example 05: SystemController — 生產級系統控制器

Demonstrates:
  - SystemController: full orchestrator with mode management + protection
  - ModeManager: priority-based strategy switching (base/override)
  - ProtectionGuard: SOC protection, reverse power protection, system alarm
  - HeartbeatService: watchdog writes with auto-pause on bypass mode
  - Bypass mode: stops all commands AND heartbeat
  - CascadingStrategy: multi-strategy power allocation (PQ + QV)
  - Auto-stop on alarm
  - EventDrivenOverride: automatic push/pop override on context conditions (v0.4.1)
  - PowerDistributor: per-device power distribution (v0.4.1)

Scenario:
  A 1MW ESS site with full production controls:
    - PQ mode as base strategy
    - QV mode added as second base (cascading)
    - SOC protection to prevent over-charge/discharge
    - Reverse power protection to prevent grid export
    - Heartbeat to keep PCS alive
    - Manual bypass for maintenance
    - Auto-stop when device alarms trigger
    - Automatic island mode override when ACB trips (EventDrivenOverride)
    - Proportional power distribution across 2 PCS units (PowerDistributor)

Architecture:
  ContextBuilder.build() → StrategyContext (+ system_alarm flag)
       ↓
  StrategyExecutor (strategy chosen by ModeManager)
       ↓
  Command → ProtectionGuard.apply() → protected Command
       ↓
  PowerDistributor.distribute() → per-device Commands
       ↓
  CommandRouter.route_per_device() → device writes
       ↓
  HeartbeatService (parallel) → watchdog writes
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, PropertyMock

from csp_lib.controller.core import SystemBase
from csp_lib.controller.strategies import (
    BypassStrategy,
    PQModeConfig,
    PQModeStrategy,
    QVConfig,
    QVStrategy,
    StopStrategy,
)
from csp_lib.controller.system import ModePriority, SOCProtection, SOCProtectionConfig
from csp_lib.controller.system.event_override import ContextKeyOverride
from csp_lib.core.health import HealthStatus
from csp_lib.integration import (
    CommandMapping,
    ContextMapping,
    DeviceRegistry,
    HeartbeatMapping,
    HeartbeatMode,
    SystemController,
    SystemControllerConfig,
)
from csp_lib.integration.distributor import ProportionalDistributor

# ============================================================
# Step 1: Setup (same pattern as example 04)
# ============================================================


def make_device(device_id, values, responsive=True, protected=False):
    dev = MagicMock()
    type(dev).device_id = PropertyMock(return_value=device_id)
    type(dev).is_connected = PropertyMock(return_value=True)
    type(dev).is_responsive = PropertyMock(return_value=responsive)
    type(dev).is_protected = PropertyMock(return_value=protected)
    type(dev).is_healthy = PropertyMock(return_value=not protected)
    type(dev).latest_values = PropertyMock(return_value=values)
    type(dev).active_alarms = PropertyMock(return_value=[])
    dev.write = AsyncMock()
    dev.has_capability = lambda c: False
    type(dev).capabilities = PropertyMock(return_value={})

    def health():
        from csp_lib.core.health import HealthReport

        return HealthReport(
            status=HealthStatus.HEALTHY if not protected else HealthStatus.DEGRADED,
            component=f"device:{device_id}",
            details={},
        )

    dev.health = health
    return dev


def setup():
    meter = make_device("meter_01", {"voltage": 380.0, "frequency": 60.0, "active_power": 30.0})
    pcs_1 = make_device("pcs_01", {})
    pcs_2 = make_device("pcs_02", {})
    bms = make_device("bms_01", {"soc": 80.0})

    registry = DeviceRegistry()
    registry.register(meter, traits=["meter"])
    registry.register(pcs_1, traits=["pcs"])
    registry.register(pcs_2, traits=["pcs"])
    registry.register(bms, traits=["bms"])
    return registry


# ============================================================
# Step 2: Configure SystemController
# ============================================================


async def main():
    registry = setup()

    config = SystemControllerConfig(
        # --- Context Mappings (same as GridControlLoop) ---
        context_mappings=[
            ContextMapping(point_name="soc", context_field="soc", trait="bms"),
            ContextMapping(point_name="voltage", context_field="extra.voltage", trait="meter"),
            ContextMapping(point_name="frequency", context_field="extra.frequency", trait="meter"),
            ContextMapping(point_name="active_power", context_field="extra.meter_power", trait="meter"),
        ],
        # --- Command Mappings ---
        command_mappings=[
            CommandMapping(command_field="p_target", point_name="p_set", trait="pcs"),
            CommandMapping(command_field="q_target", point_name="q_set", trait="pcs"),
        ],
        # --- System Base ---
        system_base=SystemBase(p_base=1000.0, q_base=500.0),
        # --- Protection Rules ---
        protection_rules=[
            SOCProtection(SOCProtectionConfig(soc_high=95.0, soc_low=5.0, warning_band=5.0)),
            # ReversePowerProtection(...),  # Uncomment for reverse power protection
            # SystemAlarmProtection(),       # Uncomment for system alarm protection
        ],
        # --- Alarm Handling ---
        auto_stop_on_alarm=True,  # Push StopStrategy when any device alarms
        alarm_mode="system_wide",  # "system_wide" or "per_device"
        # --- Heartbeat (NEW) ---
        heartbeat_mappings=[
            HeartbeatMapping(point_name="heartbeat", trait="pcs", mode=HeartbeatMode.TOGGLE),
        ],
        heartbeat_interval=1.0,
        # --- Cascading ---
        capacity_kva=1000.0,  # Max apparent power for cascading (kVA)
    )

    controller = SystemController(registry, config)

    # ========================================================
    # Step 3: Register Modes (註冊模式)
    # ========================================================

    # Base modes (priority 10 = SCHEDULE tier)
    controller.register_mode("pq", PQModeStrategy(PQModeConfig(p=500.0, q=0.0)), ModePriority.SCHEDULE)
    controller.register_mode("qv", QVStrategy(QVConfig(nominal_voltage=380.0, droop=5.0)), ModePriority.SCHEDULE)

    # Override modes (higher priority)
    controller.register_mode("bypass", BypassStrategy(), ModePriority.MANUAL)  # priority 50
    controller.register_mode("emergency_stop", StopStrategy(), ModePriority.PROTECTION)  # priority 100

    # Set initial base mode
    await controller.set_base_mode("pq")

    # ========================================================
    # Step 4: Run the Controller
    # ========================================================

    async with controller:
        print(f"Controller running: {controller.is_running}")
        print(f"Current mode: {controller.effective_mode_name}")
        print(f"Heartbeat running: {controller.heartbeat.is_running}")

        # Let PQ mode run for a few cycles
        await asyncio.sleep(2)

        # ---- Add QV as second base mode → CascadingStrategy ----
        print("\n--- Adding QV as second base mode (cascading) ---")
        await controller.add_base_mode("qv")
        print(f"Mode: {controller.effective_mode_name}")
        # Now PQ + QV run together, constrained by 1000 kVA capacity
        await asyncio.sleep(2)

        # ---- Push bypass override → stops commands + heartbeat ----
        print("\n--- Entering bypass mode (maintenance) ---")
        await controller.push_override("bypass")
        print(f"Mode: {controller.effective_mode_name}")
        print(f"Heartbeat paused: {controller.heartbeat.is_paused}")
        # Commands stop, heartbeat stops → PCS enters safe mode
        await asyncio.sleep(2)

        # ---- Pop bypass → resumes normal operation ----
        print("\n--- Exiting bypass mode ---")
        await controller.pop_override("bypass")
        print(f"Mode: {controller.effective_mode_name}")
        print(f"Heartbeat paused: {controller.heartbeat.is_paused}")
        await asyncio.sleep(2)

        # ---- Check protection status ----
        result = controller.protection_status
        if result:
            print(f"\nProtection result: triggered_rules={result.triggered_rules}")
            print(f"  Original command: {result.original_command}")
            print(f"  Protected command: {result.protected_command}")

        # ---- Health check ----
        health = controller.health()
        print(f"\nSystem health: {health.status.name}")
        for child in health.children:
            print(f"  {child.component}: {child.status.name}")

    print("\nController stopped.")


# ============================================================
# Demo: EventDrivenOverride — automatic override on context condition
# ============================================================


async def demo_event_driven_override():
    """
    Demonstrates EventDrivenOverride: automatically push/pop override
    when a context condition is met, without manual push_override() calls.

    Scenario: ACB trips (acb_tripped=True in context) → auto enter island mode.
    """
    print("\n" + "=" * 60)
    print("Demo: EventDrivenOverride (auto island on ACB trip)")
    print("=" * 60)

    registry = setup()

    island_strategy = StopStrategy()  # Use StopStrategy as island stand-in

    config = SystemControllerConfig(
        context_mappings=[
            ContextMapping(point_name="soc", context_field="soc", trait="bms"),
        ],
        command_mappings=[
            CommandMapping(command_field="p_target", point_name="p_set", trait="pcs"),
        ],
        system_base=SystemBase(p_base=1000.0),
        auto_stop_on_alarm=False,  # Disable default AlarmStopOverride for clarity
    )

    controller = SystemController(registry, config)
    controller.register_mode("pq", PQModeStrategy(PQModeConfig(p=500.0)), ModePriority.SCHEDULE)
    controller.register_mode("island", island_strategy, ModePriority.PROTECTION)

    # Register EventDrivenOverride: auto-enter "island" when acb_tripped is True
    acb_override = ContextKeyOverride(
        name="island",
        context_key="acb_tripped",
        activate_when=lambda v: v is True,
        cooldown_seconds=2.0,  # 2s cooldown after condition clears
    )
    controller.register_event_override(acb_override)

    await controller.set_base_mode("pq")

    async with controller:
        print(f"  Initial mode: {controller.effective_mode_name}")
        await asyncio.sleep(1)
        print(f"  Event overrides registered: {[o.name for o in controller.event_overrides]}")

    print("  EventDrivenOverride demo complete.")


# ============================================================
# Demo: PowerDistributor — per-device proportional power distribution
# ============================================================


async def demo_power_distributor():
    """
    Demonstrates ProportionalDistributor: distribute system-level Command
    to multiple PCS devices proportional to their rated power.

    Device setup:
      pcs_01: rated_p=500kW → receives 1/3 of total
      pcs_02: rated_p=1000kW → receives 2/3 of total
    """
    print("\n" + "=" * 60)
    print("Demo: PowerDistributor (proportional to rated_p)")
    print("=" * 60)

    meter = make_device("meter_01", {"voltage": 380.0, "frequency": 60.0, "active_power": 30.0})
    pcs_1 = make_device("pcs_01", {})
    pcs_2 = make_device("pcs_02", {})
    bms = make_device("bms_01", {"soc": 60.0})

    registry = DeviceRegistry()
    registry.register(meter, traits=["meter"])
    # Register with rated_p metadata for ProportionalDistributor
    registry.register(pcs_1, traits=["pcs"], metadata={"rated_p": 500.0})
    registry.register(pcs_2, traits=["pcs"], metadata={"rated_p": 1000.0})
    registry.register(bms, traits=["bms"])

    config = SystemControllerConfig(
        context_mappings=[
            ContextMapping(point_name="soc", context_field="soc", trait="bms"),
        ],
        command_mappings=[
            CommandMapping(command_field="p_target", point_name="p_set", trait="pcs"),
        ],
        system_base=SystemBase(p_base=1500.0),
        # Enable ProportionalDistributor: split 1500kW command proportionally
        power_distributor=ProportionalDistributor(rated_key="rated_p"),
    )

    controller = SystemController(registry, config)
    controller.register_mode("pq", PQModeStrategy(PQModeConfig(p=1500.0)), ModePriority.SCHEDULE)
    await controller.set_base_mode("pq")

    async with controller:
        await asyncio.sleep(2)
        print("  Power distribution (rated_p: pcs_01=500kW, pcs_02=1000kW):")
        print("    pcs_01 receives: ~500kW (1/3 of 1500kW)")
        print("    pcs_02 receives: ~1000kW (2/3 of 1500kW)")
        print(f"  Controller running: {controller.is_running}")

    print("  PowerDistributor demo complete.")


# ============================================================
# Mode Priority Cheat Sheet:
#
#   ModePriority.SCHEDULE   = 10   (normal operation)
#   ModePriority.MANUAL     = 50   (operator override)
#   ModePriority.PROTECTION = 100  (safety override)
#   Auto-stop               = 101  (highest, auto-managed)
#
# The HIGHEST priority override always wins.
# When no overrides: base mode(s) run.
# Multiple base modes → CascadingStrategy (if capacity_kva is set).
# ============================================================


async def run_all():
    await main()
    await demo_event_driven_override()
    await demo_power_distributor()


if __name__ == "__main__":
    asyncio.run(run_all())
