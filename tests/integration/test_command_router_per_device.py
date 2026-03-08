"""Tests for CommandRouter.route_per_device() method."""

from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from csp_lib.controller.core import Command
from csp_lib.integration.command_router import CommandRouter
from csp_lib.integration.registry import DeviceRegistry
from csp_lib.integration.schema import CapabilityCommandMapping, CommandMapping

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_device(device_id: str, responsive: bool = True, protected: bool = False) -> MagicMock:
    dev = MagicMock()
    type(dev).device_id = PropertyMock(return_value=device_id)
    type(dev).is_responsive = PropertyMock(return_value=responsive)
    type(dev).is_protected = PropertyMock(return_value=protected)
    dev.write = AsyncMock()
    return dev


def _make_capable_device(
    device_id: str,
    responsive: bool = True,
    protected: bool = False,
    capabilities: list | None = None,
    point_map: dict | None = None,
) -> MagicMock:
    dev = MagicMock()
    type(dev).device_id = PropertyMock(return_value=device_id)
    type(dev).is_responsive = PropertyMock(return_value=responsive)
    type(dev).is_protected = PropertyMock(return_value=protected)
    dev.write = AsyncMock()
    dev.has_capability = MagicMock(side_effect=lambda cap: cap in (capabilities or []))
    dev.resolve_point = MagicMock(side_effect=lambda cap, slot: (point_map or {}).get((cap, slot), f"{cap}_{slot}"))
    return dev


def _make_capability(name: str, write_slots: list[str]) -> MagicMock:
    cap = MagicMock()
    cap.name = name
    cap.write_slots = write_slots
    return cap


# ===========================================================================
# route_per_device tests
# ===========================================================================


class TestRoutePerDeviceExplicitMappings:
    """Explicit CommandMapping uses system-level command (same as route())."""

    @pytest.mark.asyncio
    async def test_explicit_mapping_uses_system_command(self):
        reg = DeviceRegistry()
        dev = _make_device("pcs1")
        reg.register(dev)

        mapping = CommandMapping(command_field="p_target", point_name="p_set", device_id="pcs1")
        router = CommandRouter(reg, [mapping])

        system_cmd = Command(p_target=1000.0, q_target=500.0)
        per_device = {"pcs1": Command(p_target=333.0, q_target=166.0)}

        await router.route_per_device(system_cmd, per_device)
        # Explicit mapping should use system_cmd, not per_device value
        dev.write.assert_awaited_once_with("p_set", 1000.0)

    @pytest.mark.asyncio
    async def test_explicit_mapping_with_transform(self):
        reg = DeviceRegistry()
        dev = _make_device("pcs1")
        reg.register(dev)

        mapping = CommandMapping(
            command_field="p_target",
            point_name="p_set",
            device_id="pcs1",
            transform=lambda v: v * 0.5,
        )
        router = CommandRouter(reg, [mapping])

        await router.route_per_device(Command(p_target=1000.0), {"pcs1": Command(p_target=500.0)})
        dev.write.assert_awaited_once_with("p_set", 500.0)

    @pytest.mark.asyncio
    async def test_explicit_trait_broadcast(self):
        reg = DeviceRegistry()
        d1 = _make_device("d1")
        d2 = _make_device("d2")
        reg.register(d1, traits=["pcs"])
        reg.register(d2, traits=["pcs"])

        mapping = CommandMapping(command_field="p_target", point_name="p_set", trait="pcs")
        router = CommandRouter(reg, [mapping])

        system_cmd = Command(p_target=1000.0)
        per_device = {"d1": Command(p_target=500.0), "d2": Command(p_target=500.0)}

        await router.route_per_device(system_cmd, per_device)
        d1.write.assert_awaited_once_with("p_set", 1000.0)
        d2.write.assert_awaited_once_with("p_set", 1000.0)


class TestRoutePerDeviceCapabilityMappings:
    """Capability mappings use per_device_commands."""

    @pytest.mark.asyncio
    async def test_capability_mapping_uses_per_device_command(self):
        cap = _make_capability("p_control", write_slots=["p_set"])
        reg = DeviceRegistry()
        dev = _make_capable_device("d1", capabilities=[cap], point_map={(cap, "p_set"): "actual_p_reg"})
        reg.register(dev)

        cap_mapping = CapabilityCommandMapping(command_field="p_target", capability=cap, slot="p_set")
        router = CommandRouter(reg, [], capability_mappings=[cap_mapping])

        system_cmd = Command(p_target=1000.0)
        per_device = {"d1": Command(p_target=333.0)}

        await router.route_per_device(system_cmd, per_device)
        dev.write.assert_awaited_once_with("actual_p_reg", 333.0)

    @pytest.mark.asyncio
    async def test_device_not_in_per_device_commands_is_skipped(self):
        cap = _make_capability("p_control", write_slots=["p_set"])
        reg = DeviceRegistry()
        dev = _make_capable_device("d1", capabilities=[cap])
        reg.register(dev)

        cap_mapping = CapabilityCommandMapping(command_field="p_target", capability=cap, slot="p_set")
        router = CommandRouter(reg, [], capability_mappings=[cap_mapping])

        system_cmd = Command(p_target=1000.0)
        per_device = {}  # d1 not included

        await router.route_per_device(system_cmd, per_device)
        dev.write.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_protected_device_is_skipped(self):
        cap = _make_capability("p_control", write_slots=["p_set"])
        reg = DeviceRegistry()
        dev = _make_capable_device("d1", protected=True, capabilities=[cap])
        reg.register(dev)

        cap_mapping = CapabilityCommandMapping(command_field="p_target", capability=cap, slot="p_set")
        router = CommandRouter(reg, [], capability_mappings=[cap_mapping])

        await router.route_per_device(Command(p_target=1000.0), {"d1": Command(p_target=500.0)})
        dev.write.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_non_responsive_device_is_skipped(self):
        cap = _make_capability("p_control", write_slots=["p_set"])
        reg = DeviceRegistry()
        dev = _make_capable_device("d1", responsive=False, capabilities=[cap])
        reg.register(dev)

        cap_mapping = CapabilityCommandMapping(command_field="p_target", capability=cap, slot="p_set")
        router = CommandRouter(reg, [], capability_mappings=[cap_mapping])

        await router.route_per_device(Command(p_target=1000.0), {"d1": Command(p_target=500.0)})
        dev.write.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_device_lacking_capability_is_skipped(self):
        cap = _make_capability("p_control", write_slots=["p_set"])
        reg = DeviceRegistry()
        # Device does NOT have the required capability
        dev = _make_capable_device("d1", capabilities=[])
        reg.register(dev)

        cap_mapping = CapabilityCommandMapping(command_field="p_target", capability=cap, slot="p_set")
        router = CommandRouter(reg, [], capability_mappings=[cap_mapping])

        await router.route_per_device(Command(p_target=1000.0), {"d1": Command(p_target=500.0)})
        dev.write.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_transform_applied_before_write(self):
        cap = _make_capability("p_control", write_slots=["p_set"])
        reg = DeviceRegistry()
        dev = _make_capable_device("d1", capabilities=[cap], point_map={(cap, "p_set"): "p_reg"})
        reg.register(dev)

        cap_mapping = CapabilityCommandMapping(
            command_field="p_target",
            capability=cap,
            slot="p_set",
            transform=lambda v: v * 10,
        )
        router = CommandRouter(reg, [], capability_mappings=[cap_mapping])

        await router.route_per_device(Command(p_target=1000.0), {"d1": Command(p_target=100.0)})
        dev.write.assert_awaited_once_with("p_reg", 1000.0)  # 100 * 10

    @pytest.mark.asyncio
    async def test_multiple_devices_with_per_device_commands(self):
        cap = _make_capability("p_control", write_slots=["p_set"])
        reg = DeviceRegistry()
        d1 = _make_capable_device("d1", capabilities=[cap], point_map={(cap, "p_set"): "p_reg"})
        d2 = _make_capable_device("d2", capabilities=[cap], point_map={(cap, "p_set"): "p_reg"})
        reg.register(d1)
        reg.register(d2)

        cap_mapping = CapabilityCommandMapping(command_field="p_target", capability=cap, slot="p_set")
        router = CommandRouter(reg, [], capability_mappings=[cap_mapping])

        per_device = {
            "d1": Command(p_target=600.0),
            "d2": Command(p_target=400.0),
        }
        await router.route_per_device(Command(p_target=1000.0), per_device)
        d1.write.assert_awaited_once_with("p_reg", 600.0)
        d2.write.assert_awaited_once_with("p_reg", 400.0)

    @pytest.mark.asyncio
    async def test_capability_with_device_id_scope(self):
        """CapabilityCommandMapping with explicit device_id."""
        cap = _make_capability("p_control", write_slots=["p_set"])
        reg = DeviceRegistry()
        dev = _make_capable_device("d1", capabilities=[cap], point_map={(cap, "p_set"): "p_reg"})
        reg.register(dev)

        cap_mapping = CapabilityCommandMapping(command_field="p_target", capability=cap, slot="p_set", device_id="d1")
        router = CommandRouter(reg, [], capability_mappings=[cap_mapping])

        await router.route_per_device(Command(p_target=1000.0), {"d1": Command(p_target=750.0)})
        dev.write.assert_awaited_once_with("p_reg", 750.0)

    @pytest.mark.asyncio
    async def test_capability_with_trait_scope(self):
        """CapabilityCommandMapping with trait scope."""
        cap = _make_capability("p_control", write_slots=["p_set"])
        reg = DeviceRegistry()
        d1 = _make_capable_device("d1", capabilities=[cap], point_map={(cap, "p_set"): "p_reg"})
        d2 = _make_capable_device("d2", capabilities=[cap], point_map={(cap, "p_set"): "p_reg"})
        reg.register(d1, traits=["pcs"])
        reg.register(d2, traits=["pcs"])

        cap_mapping = CapabilityCommandMapping(command_field="p_target", capability=cap, slot="p_set", trait="pcs")
        router = CommandRouter(reg, [], capability_mappings=[cap_mapping])

        per_device = {"d1": Command(p_target=600.0), "d2": Command(p_target=400.0)}
        await router.route_per_device(Command(p_target=1000.0), per_device)
        d1.write.assert_awaited_once_with("p_reg", 600.0)
        d2.write.assert_awaited_once_with("p_reg", 400.0)
